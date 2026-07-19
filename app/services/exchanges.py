"""Multi-exchange public market data: Binance, Bybit fallback, Hyperliquid, Kraken."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.services import bybit as bybit_svc
from app.services.assets import HL_COINS, KRAKEN_SYMBOLS, PERP_SYMBOLS, is_crypto
from app.services.binance import (
    FAPI,
    FUTURES_DATA,
    TIMEOUT,
    fetch_funding_rate,
    fetch_global_ls_ratio,
    fetch_klines,
    fetch_open_interest,
    fetch_taker_ls_ratio,
    fetch_ticker,
    fetch_top_trader_ls_ratio,
    fetch_top_trader_position_ratio,
)

HL_INFO = "https://api.hyperliquid.xyz/info"
KRAKEN_TICKERS = "https://futures.kraken.com/derivatives/api/v3/tickers"

BINANCE_SYMBOLS = PERP_SYMBOLS


from app.services.http_util import get_json, post_json


async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> Any:
    return await get_json(client, url, params, retries=2, label=url)


async def _post(client: httpx.AsyncClient, url: str, body: dict) -> Any:
    return await post_json(client, url, body, retries=2)


async def fetch_binance_oi_value(client: httpx.AsyncClient, symbol: str) -> dict:
    raw = await _get(
        client,
        f"{FUTURES_DATA}/openInterestHist",
        {"symbol": symbol, "period": "5m", "limit": 1},
    )
    if not raw:
        oi = await fetch_open_interest(client, symbol)
        return {
            "oi_base": oi["open_interest"],
            "oi_usd": None,
            "time": oi["time"],
        }
    row = raw[-1]
    return {
        "oi_base": float(row["sumOpenInterest"]),
        "oi_usd": float(row["sumOpenInterestValue"]),
        "time": int(row["timestamp"]),
    }


async def fetch_hyperliquid_all(client: httpx.AsyncClient) -> dict[str, dict]:
    data = await _post(client, HL_INFO, {"type": "metaAndAssetCtxs"})
    universe = data[0]["universe"]
    ctxs = data[1]
    name_to_idx = {u["name"]: i for i, u in enumerate(universe)}

    out: dict[str, dict] = {}
    for asset, coin in HL_COINS.items():
        idx = name_to_idx.get(coin)
        if idx is None:
            out[asset] = {"ok": False, "error": f"{coin} not listed"}
            continue
        ctx = ctxs[idx]
        mark = float(ctx.get("markPx") or 0)
        oi_base = float(ctx.get("openInterest") or 0)
        funding = float(ctx.get("funding") or 0)
        day_ntl = float(ctx.get("dayNtlVlm") or 0)
        premium = float(ctx.get("premium") or 0) if ctx.get("premium") is not None else None
        out[asset] = {
            "ok": True,
            "exchange": "hyperliquid",
            "symbol": coin,
            "mark_price": mark,
            "oi_base": oi_base,
            "oi_usd": oi_base * mark if mark else None,
            "funding_rate": funding,
            "volume_24h_usd": day_ntl,
            "premium": premium,
            "oracle_price": float(ctx["oraclePx"]) if ctx.get("oraclePx") else None,
        }
    return out


async def fetch_kraken_all(client: httpx.AsyncClient) -> dict[str, dict]:
    data = await _get(client, KRAKEN_TICKERS)
    tickers = {t["symbol"]: t for t in data.get("tickers", [])}

    out: dict[str, dict] = {}
    for asset, symbol in KRAKEN_SYMBOLS.items():
        t = tickers.get(symbol)
        if not t:
            out[asset] = {"ok": False, "error": f"{symbol} not found"}
            continue
        mark = float(t.get("markPrice") or t.get("last") or 0)
        oi_base = float(t.get("openInterest") or 0)
        oi_usd = oi_base * mark if mark else None
        funding = float(t.get("fundingRate") or 0)
        vol_quote = float(t.get("volumeQuote") or 0)
        out[asset] = {
            "ok": True,
            "exchange": "kraken",
            "symbol": symbol,
            "mark_price": mark,
            "oi_base": oi_base,
            "oi_usd": oi_usd,
            "funding_rate": funding,
            "volume_24h_usd": vol_quote,
            "index_price": float(t["indexPrice"]) if t.get("indexPrice") is not None else None,
            "change_24h": float(t["change24h"]) if t.get("change24h") is not None else None,
        }
    return out


def _estimate_ls_notional(
    oi_usd: float | None,
    long_pct: float,
    short_pct: float,
) -> dict:
    if oi_usd is None or oi_usd <= 0:
        return {
            "long_notional_usd": None,
            "short_notional_usd": None,
            "total_notional_usd": None,
        }
    long_n = oi_usd * (long_pct / 100.0)
    short_n = oi_usd * (short_pct / 100.0)
    return {
        "long_notional_usd": long_n,
        "short_notional_usd": short_n,
        "total_notional_usd": oi_usd,
    }


async def fetch_binance_exchange_slice(
    client: httpx.AsyncClient, asset: str, symbol: str
) -> dict:
    # 요청을 3묶음으로 나눠 429 완화 (한 심볼에 11개 동시 호출 금지)
    ticker, global_ls, funding, oi_live = await asyncio.gather(
        fetch_ticker(client, symbol),
        fetch_global_ls_ratio(client, symbol),
        fetch_funding_rate(client, symbol),
        fetch_open_interest(client, symbol),
    )
    top_account, top_position, taker, oi_val = await asyncio.gather(
        fetch_top_trader_ls_ratio(client, symbol),
        fetch_top_trader_position_ratio(client, symbol),
        fetch_taker_ls_ratio(client, symbol),
        fetch_binance_oi_value(client, symbol),
    )
    k4, k1d, k1h = await asyncio.gather(
        fetch_klines(client, symbol, "4h", 200),
        fetch_klines(client, symbol, "1d", 120),
        fetch_klines(client, symbol, "1h", 100),
    )

    g = global_ls[-1] if global_ls else None
    tp = top_position[-1] if top_position else None
    ta = top_account[-1] if top_account else None
    tk = taker[-1] if taker else None

    global_long_pct = (g["long_account"] * 100) if g else 50.0
    global_short_pct = (g["short_account"] * 100) if g else 50.0
    pos_long_pct = (tp["long_account"] * 100) if tp else global_long_pct
    pos_short_pct = (tp["short_account"] * 100) if tp else global_short_pct

    oi_usd = oi_val.get("oi_usd")
    if oi_usd is None and funding.get("mark_price"):
        oi_usd = oi_live["open_interest"] * float(funding["mark_price"])

    pos_notional = _estimate_ls_notional(oi_usd, pos_long_pct, pos_short_pct)
    acct_notional = _estimate_ls_notional(oi_usd, global_long_pct, global_short_pct)

    price = float(ticker["price"])
    taker_buy = float(tk["buy_vol"]) if tk else None
    taker_sell = float(tk["sell_vol"]) if tk else None
    taker_buy_usd = taker_buy * price if taker_buy is not None else None
    taker_sell_usd = taker_sell * price if taker_sell is not None else None

    return {
        "ok": True,
        "exchange": "binance",
        "symbol": symbol,
        "price": price,
        "mark_price": float(funding["mark_price"]),
        "change_24h_pct": float(ticker["change_pct"]),
        "high_24h": float(ticker["high"]),
        "low_24h": float(ticker["low"]),
        "volume_24h_base": float(ticker["volume"]),
        "volume_24h_usd": float(ticker["quote_volume"]),
        "funding_rate": float(funding["last_funding_rate"]),
        "oi_base": float(oi_val.get("oi_base") or oi_live["open_interest"]),
        "oi_usd": oi_usd,
        "global_long_pct": global_long_pct,
        "global_short_pct": global_short_pct,
        "global_ls_ratio": g["long_short_ratio"] if g else 1.0,
        "top_account_long_pct": (ta["long_account"] * 100) if ta else None,
        "top_account_ls_ratio": ta["long_short_ratio"] if ta else None,
        "top_position_long_pct": pos_long_pct,
        "top_position_short_pct": pos_short_pct,
        "top_position_ls_ratio": tp["long_short_ratio"] if tp else None,
        "taker_buy_sell_ratio": tk["buy_sell_ratio"] if tk else None,
        "taker_buy_vol_base": taker_buy,
        "taker_sell_vol_base": taker_sell,
        "taker_buy_usd": taker_buy_usd,
        "taker_sell_usd": taker_sell_usd,
        "long_notional_usd": acct_notional["long_notional_usd"],
        "short_notional_usd": acct_notional["short_notional_usd"],
        "pos_long_notional_usd": pos_notional["long_notional_usd"],
        "pos_short_notional_usd": pos_notional["short_notional_usd"],
        "notional_note": "OI × 계정/포지션 비율 추정 (계약상 롱=숏 OI는 동일, 비중 추정용)",
        "_raw": {
            "ticker": ticker,
            "global_ls": global_ls,
            "top_account_ls": top_account,
            "top_position_ls": top_position,
            "taker_ls": taker,
            "open_interest": oi_live,
            "funding": funding,
            "klines_4h": k4,
            "klines_1d": k1d,
            "klines_1h": k1h,
        },
    }


def _side_for_asset(side_all: dict | Exception | None, asset: str) -> dict:
    if isinstance(side_all, Exception):
        return {"ok": False, "error": str(side_all)}
    if not isinstance(side_all, dict):
        return {"ok": False, "error": "no data"}
    row = side_all.get(asset)
    if not row:
        return {"ok": False, "error": "not listed"}
    return row


async def fetch_symbol_bundle(
    asset: str,
    *,
    client: httpx.AsyncClient | None = None,
    hl_all: dict | None = None,
    kr_all: dict | None = None,
    prefer_bybit: bool = False,
) -> dict:
    """
    Full multi-exchange bundle for one asset (crypto or TradFi stock perp).

    Primary: Binance (L/S, klines…) → 실패/429 시 Bybit
    Side (crypto only): Hyperliquid, Kraken OI / funding / volume
    """
    asset = asset.upper()

    headers = {
        "User-Agent": "longshort-han-nune/1.0 (+https://github.com/JimProKing/longshort-han-nune)",
        "Accept": "application/json",
    }

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=TIMEOUT, headers=headers, follow_redirects=True)

    assert client is not None
    try:
        if asset not in BINANCE_SYMBOLS:
            raise ValueError(f"Unsupported asset: {asset}")
        symbol = BINANCE_SYMBOLS[asset]
        crypto = is_crypto(asset)

        # TradFi stock perps are not on HL/Kraken — skip side exchange bulk fetch
        if crypto and (hl_all is None or kr_all is None):
            hl_task = asyncio.create_task(fetch_hyperliquid_all(client))
            kr_task = asyncio.create_task(fetch_kraken_all(client))
        else:
            hl_task = kr_task = None
            if not crypto:
                hl_all = hl_all if isinstance(hl_all, dict) else {}
                kr_all = kr_all if isinstance(kr_all, dict) else {}

        primary = None
        primary_err = None
        source = "binance"

        async def _try_binance():
            return await fetch_binance_exchange_slice(client, asset, symbol)

        async def _try_bybit():
            return await bybit_svc.fetch_primary_slice(client, asset, symbol)

        order = (_try_bybit, _try_binance) if prefer_bybit else (_try_binance, _try_bybit)
        names = ("bybit", "binance") if prefer_bybit else ("binance", "bybit")

        for fn, name in zip(order, names):
            try:
                primary = await fn()
                source = name
                break
            except Exception as e:
                msg = f"{name.title()}: {type(e).__name__}: {e}"
                primary_err = f"{primary_err} | {msg}" if primary_err else msg
                continue

        if primary is None:
            if hl_task and kr_task:
                await asyncio.gather(hl_task, kr_task, return_exceptions=True)
            raise RuntimeError(f"{asset} 주요 데이터 실패 | {primary_err}")

        if hl_task and kr_task:
            loaded_hl, loaded_kr = await asyncio.gather(hl_task, kr_task, return_exceptions=True)
            if hl_all is None:
                hl_all = loaded_hl if isinstance(loaded_hl, dict) else loaded_hl
            if kr_all is None:
                kr_all = loaded_kr if isinstance(loaded_kr, dict) else loaded_kr
    finally:
        if owns_client:
            await client.aclose()

    raw = primary.pop("_raw")
    hl = _side_for_asset(hl_all, asset)
    kr = _side_for_asset(kr_all, asset)

    if source == "binance":
        bn_card = {**primary, "ok": True}
        bybit_card = {"ok": False, "error": "primary는 Binance (Bybit 미조회)"}
    else:
        short_err = primary_err or "Binance 실패 — Bybit 폴백"
        # 429 메시지는 짧게
        if "429" in short_err:
            short_err = "Binance rate limit (429) — Bybit 사용 중"
        bn_card = {"ok": False, "error": short_err, "exchange": "binance"}
        bybit_card = {**primary, "ok": True, "exchange": "bybit"}

    exchanges = {
        "binance": bn_card,
        "bybit": bybit_card,
        "hyperliquid": hl,
        "kraken": kr,
    }

    oi_parts: list[float] = []
    if primary.get("oi_usd"):
        oi_parts.append(float(primary["oi_usd"]))
    if isinstance(hl, dict) and hl.get("ok") and hl.get("oi_usd"):
        oi_parts.append(float(hl["oi_usd"]))
    if isinstance(kr, dict) and kr.get("ok") and kr.get("oi_usd"):
        oi_parts.append(float(kr["oi_usd"]))
    total_oi_usd = sum(oi_parts) if oi_parts else None

    from app.services.assets import asset_type as _asset_type

    return {
        "asset": asset,
        "symbol": symbol,
        "primary_source": source,
        "primary_error": primary_err,
        "asset_type": _asset_type(asset),
        "currency": "USD",
        "ticker": raw["ticker"],
        "klines_4h": raw.get("klines_4h") or [],
        "klines_1d": raw.get("klines_1d") or [],
        "klines_1h": raw.get("klines_1h") or [],
        "global_ls": raw["global_ls"],
        "top_account_ls": raw["top_account_ls"],
        "top_position_ls": raw["top_position_ls"],
        "taker_ls": raw["taker_ls"],
        "open_interest": raw["open_interest"],
        "funding": raw["funding"],
        "exchanges": exchanges,
        "total_oi_usd": total_oi_usd,
    }
