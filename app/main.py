"""Crypto perpetual Long/Short analyzer — FastAPI app."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.services.analysis import analyze_symbol
from app.services.binance import SYMBOLS
from app.services.exchanges import fetch_symbol_bundle
from app.services.strategy import build_strategies

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Crypto LS Analyzer",
    description="BTC / ETH / XRP 무기한 롱숏 비율 · 지지선 · 전략 분석",
    version="1.0.0",
)

# Simple in-memory cache (Railway single instance OK)
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SEC = 45


async def _analyze_one(asset: str) -> dict:
    symbol = SYMBOLS[asset]
    try:
        bundle = await fetch_symbol_bundle(asset)
        analysis = analyze_symbol(bundle)
        strategies = build_strategies(analysis)
        return {
            "asset": asset,
            "symbol": symbol,
            "analysis": analysis,
            "strategies": strategies,
            "updated_at": int(time.time() * 1000),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{asset} 데이터 조회 실패: {e}") from e


@app.get("/api/health")
async def health():
    return {"ok": True, "assets": list(SYMBOLS.keys())}


@app.get("/api/analyze")
async def analyze_all(
    refresh: bool = Query(False, description="캐시 무시하고 강제 갱신"),
):
    cache_key = "all"
    now = time.time()
    if not refresh and cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < CACHE_TTL_SEC:
            data = {**data, "cached": True, "cache_age_sec": int(now - ts)}
            return data

    results = await asyncio.gather(
        _analyze_one("BTC"),
        _analyze_one("ETH"),
        _analyze_one("XRP"),
        return_exceptions=True,
    )

    coins = []
    errors = []
    for asset, res in zip(["BTC", "ETH", "XRP"], results):
        if isinstance(res, Exception):
            errors.append({"asset": asset, "error": str(res)})
        else:
            coins.append(res)

    if not coins:
        raise HTTPException(status_code=502, detail={"message": "전체 조회 실패", "errors": errors})

    payload = {
        "coins": coins,
        "errors": errors,
        "cached": False,
        "source": "Binance · Hyperliquid · Kraken Futures",
        "generated_at": int(now * 1000),
    }
    _cache[cache_key] = (now, payload)
    return payload


@app.get("/api/analyze/{asset}")
async def analyze_asset(asset: str, refresh: bool = False):
    asset = asset.upper()
    if asset not in SYMBOLS:
        raise HTTPException(status_code=404, detail=f"지원 자산: {list(SYMBOLS.keys())}")

    cache_key = asset
    now = time.time()
    if not refresh and cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < CACHE_TTL_SEC:
            return {**data, "cached": True}

    data = await _analyze_one(asset)
    _cache[cache_key] = (now, data)
    return {**data, "cached": False}


# Static frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_path)
