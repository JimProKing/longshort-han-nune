"""Crypto perpetual Long/Short analyzer — FastAPI app."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.services.analysis import analyze_symbol
from app.services.assets import ASSET_ORDER, ASSET_META, assert_known, display_symbol, is_crypto
from app.services.binance import TIMEOUT
from app.services.exchanges import (
    fetch_hyperliquid_all,
    fetch_kraken_all,
    fetch_symbol_bundle,
)
from app.services.ocn import fetch_ocn_schedule
from app.services.strategy import build_strategies

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Crypto LS Analyzer",
    description="코인 무기한 롱숏 · 국내주식 지지/저항 · 진입 시나리오",
    version="1.1.0",
)

# In-memory cache (Railway single instance)
# Keep short so frontend auto-poll sees fresh L/S (5m buckets + OI/price).
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SEC = 45

# After Binance 429, prefer Bybit for a while
_prefer_bybit_until = 0.0
PREFER_BYBIT_COOLDOWN_SEC = 120


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={
            "User-Agent": "longshort-han-nune/1.0 (+https://github.com/JimProKing/longshort-han-nune)",
            "Accept": "application/json",
        },
        follow_redirects=True,
    )


async def _analyze_one(
    asset: str,
    *,
    client: httpx.AsyncClient,
    hl_all: dict | None,
    kr_all: dict | None,
    prefer_bybit: bool,
) -> dict:
    asset = assert_known(asset)
    symbol = display_symbol(asset)
    try:
        # Stocks don't need HL/Kraken side data
        use_hl = hl_all if is_crypto(asset) else {}
        use_kr = kr_all if is_crypto(asset) else {}
        bundle = await fetch_symbol_bundle(
            asset,
            client=client,
            hl_all=use_hl if is_crypto(asset) else {},
            kr_all=use_kr if is_crypto(asset) else {},
            prefer_bybit=prefer_bybit,
        )
        analysis = analyze_symbol(bundle)
        strategies = build_strategies(analysis)
        meta = ASSET_META.get(asset) or {}
        return {
            "asset": asset,
            "symbol": symbol,
            "name": meta.get("name_ko") or meta.get("name"),
            "asset_type": meta.get("type") or analysis.get("asset_type"),
            "currency": analysis.get("currency") or meta.get("currency"),
            "primary_source": bundle.get("primary_source"),
            "analysis": analysis,
            "strategies": strategies,
            "updated_at": int(time.time() * 1000),
        }
    except Exception as e:
        raise RuntimeError(f"{asset} 데이터 조회 실패: {e}") from e


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "assets": list(ASSET_ORDER),
        "meta": {
            a: {
                "type": ASSET_META[a]["type"],
                "name": ASSET_META[a].get("name_ko") or ASSET_META[a].get("name"),
                "currency": ASSET_META[a].get("currency"),
            }
            for a in ASSET_ORDER
        },
    }


@app.get("/api/analyze")
async def analyze_all(
    refresh: bool = Query(False, description="캐시 무시하고 강제 갱신"),
):
    global _prefer_bybit_until

    cache_key = "all"
    now = time.time()
    if not refresh and cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < CACHE_TTL_SEC:
            return {**data, "cached": True, "cache_age_sec": int(now - ts)}

    prefer_bybit = now < _prefer_bybit_until
    coins: list[dict] = []
    errors: list[dict] = []
    by_asset: dict[str, dict] = {}

    async with _client() as client:
        # HL / Kraken 은 코인마다 1번만 (TradFi 주식 퍼프에는 없음)
        hl_all, kr_all = await _load_sides(client)

        # 전체 순차 (Binance 429 방지) — 코인 + TradFi 주식 무기한
        for asset in ASSET_ORDER:
            try:
                row = await _analyze_one(
                    asset,
                    client=client,
                    hl_all=hl_all if isinstance(hl_all, dict) else None,
                    kr_all=kr_all if isinstance(kr_all, dict) else None,
                    prefer_bybit=prefer_bybit,
                )
                by_asset[asset] = row
                if row.get("primary_source") == "bybit":
                    _prefer_bybit_until = time.time() + PREFER_BYBIT_COOLDOWN_SEC
                    prefer_bybit = True
            except Exception as e:
                err = str(e)
                errors.append({"asset": asset, "error": err})
                if "429" in err:
                    _prefer_bybit_until = time.time() + PREFER_BYBIT_COOLDOWN_SEC
                    prefer_bybit = True

    coins = [by_asset[a] for a in ASSET_ORDER if a in by_asset]

    if not coins:
        err_txt = " · ".join(f"{e['asset']}: {e['error']}" for e in errors) or "unknown"
        raise HTTPException(status_code=502, detail=f"전체 조회 실패 — {err_txt}")

    sources = sorted({c.get("primary_source") for c in coins if c.get("primary_source")})
    payload = {
        "coins": coins,
        "errors": errors,
        "cached": False,
        "source": " · ".join(s.title() for s in sources if s) + " · Hyperliquid · Kraken",
        "primary_sources": sources,
        "generated_at": int(now * 1000),
    }
    _cache[cache_key] = (now, payload)
    # per-asset cache too
    for c in coins:
        _cache[c["asset"]] = (now, c)
    return payload


async def _load_sides(client: httpx.AsyncClient):
    import asyncio

    return await asyncio.gather(
        fetch_hyperliquid_all(client),
        fetch_kraken_all(client),
        return_exceptions=True,
    )


@app.get("/api/analyze/{asset}")
async def analyze_asset(asset: str, refresh: bool = False):
    global _prefer_bybit_until

    try:
        asset = assert_known(asset)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"지원 자산: {list(ASSET_ORDER)}",
        ) from None

    cache_key = asset
    now = time.time()
    if not refresh and cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < CACHE_TTL_SEC:
            return {**data, "cached": True}

    prefer_bybit = now < _prefer_bybit_until
    async with _client() as client:
        # HL/Kraken only useful for crypto; empty dict for stock perps is fine
        if is_crypto(asset):
            hl_all, kr_all = await _load_sides(client)
        else:
            hl_all, kr_all = {}, {}
        try:
            data = await _analyze_one(
                asset,
                client=client,
                hl_all=hl_all if isinstance(hl_all, dict) else None,
                kr_all=kr_all if isinstance(kr_all, dict) else None,
                prefer_bybit=prefer_bybit,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    if data.get("primary_source") == "bybit":
        _prefer_bybit_until = time.time() + PREFER_BYBIT_COOLDOWN_SEC

    _cache[cache_key] = (now, data)
    return {**data, "cached": False}


@app.get("/api/ocn/schedule")
async def ocn_schedule(refresh: bool = Query(False, description="캐시 무시하고 강제 갱신")):
    """OCN 주간 편성표 (공식 사이트 SSR 데이터)."""
    try:
        async with _client() as client:
            data = await fetch_ocn_schedule(client, force=refresh)
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OCN 편성표 조회 실패: {e}") from e


# Static frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_path)
