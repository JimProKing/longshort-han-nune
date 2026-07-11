"""Multi-exchange public market data: Binance, Hyperliquid, Kraken Futures."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.services.binance import (
    FAPI,
    FUTURES_DATA,
    SYMBOLS as BINANCE_SYMBOLS,
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

# asset -> exchange symbols
HL_COINS = {"BTC": "BTC", "ETH": "ETH", "XRP": "XRP"}
KRAKEN_SYMBOLS = {
    "BTC": "PF_XBTUSD",
    "ETH": "PF_ETHUSD",
    "XRP": "PF_XRPUSD",
}


async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> Any:
    r = await client.get(url, params=params or {})
    r.raise_for_status()
    return r.json()


async def _post(client: httpx.AsyncClient, url: str, body: dict) -> Any:
    r = await client.post(url, json=body)
    r.raise_for_status()
    return r.json()


async def fetch_binance_oi_value(client: httpx.AsyncClient, symbol: str) -> dict:
    """OI with USD notional (sumOpenInterestValue)."""
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
    """Return {BTC|ETH|XRP: metrics} from Hyperliquid metaAndAssetCtxs."""
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
    """Return {BTC|ETH|XRP: metrics} from Kraken Futures tickers (PF linear)."""
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
        # PF contracts: OI is in base asset units
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
    """
    Futures OI is matched long=short in contracts, but 'position ratio'
    (top traders) is used as a size-weighted split estimate — same approach
    retail dashboards use for 'long/short notional'.
    """
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
    (
        ticker,
        global_ls,
        top_account,
        top_position,
        taker,
        oi_live,
        oi_val,
        funding,
    ) = await asyncio.gather(
        fetch_ticker(client, symbol),
        fetch_global_ls_ratio(client, symbol, "1h", 24),
        fetch_top_trader_ls_ratio(client, symbol, "1h", 24),
        fetch_top_trader_position_ratio(client, symbol, "1h", 24),
        fetch_taker_ls_ratio(client, symbol, "1h", 24),
        fetch_open_interest(client, symbol),
        fetch_binance_oi_value(client, symbol),
        fetch_funding_rate(client, symbol),
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
    # Prefer mark for fallback notional
    if oi_usd is None and funding.get("mark_price"):
        oi_usd = oi_live["open_interest"] * float(funding["mark_price"])

    # Notional split: top trader *position* ratio × OI (more size-aware than account ratio)
    pos_notional = _estimate_ls_notional(oi_usd, pos_long_pct, pos_short_pct)
    # Also estimate by global account ratio (for display near main L/S bar)
    acct_notional = _estimate_ls_notional(oi_usd, global_long_pct, global_short_pct)

    price = float(ticker["price"])
    taker_buy = float(tk["buy_vol"]) if tk else None
    taker_sell = float(tk["sell_vol"]) if tk else None
    # taker vol is in base asset on Binance futures data API
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
        # amounts next to L/S
        "long_notional_usd": acct_notional["long_notional_usd"],
        "short_notional_usd": acct_notional["short_notional_usd"],
        "pos_long_notional_usd": pos_notional["long_notional_usd"],
        "pos_short_notional_usd": pos_notional["short_notional_usd"],
        "notional_note": "OI × 계정/포지션 비율 추정 (계약상 롱=숏 OI는 동일, 비중 추정용)",
        # raw series for analysis
        "_raw": {
            "ticker": ticker,
            "global_ls": global_ls,
            "top_account_ls": top_account,
            "top_position_ls": top_position,
            "taker_ls": taker,
            "open_interest": oi_live,
            "funding": funding,
            "oi_value": oi_val,
        },
    }


async def fetch_symbol_bundle(asset: str) -> dict:
    """Full multi-exchange bundle for one asset (BTC/ETH/XRP)."""
    asset = asset.upper()
    if asset not in BINANCE_SYMBOLS:
        raise ValueError(f"Unsupported asset: {asset}")
    symbol = BINANCE_SYMBOLS[asset]

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        bn_task = fetch_binance_exchange_slice(client, asset, symbol)
        klines_4h_t = fetch_klines(client, symbol, "4h", 200)
        klines_1d_t = fetch_klines(client, symbol, "1d", 120)
        klines_1h_t = fetch_klines(client, symbol, "1h", 100)
        hl_task = fetch_hyperliquid_all(client)
        kr_task = fetch_kraken_all(client)

        bn, k4, k1d, k1h, hl_all, kr_all = await asyncio.gather(
            bn_task,
            klines_4h_t,
            klines_1d_t,
            klines_1h_t,
            hl_task,
            kr_task,
            return_exceptions=True,
        )

    if isinstance(bn, Exception):
        raise bn

    hl = hl_all.get(asset) if isinstance(hl_all, dict) else {"ok": False, "error": str(hl_all)}
    kr = kr_all.get(asset) if isinstance(kr_all, dict) else {"ok": False, "error": str(kr_all)}
    if isinstance(hl_all, Exception):
        hl = {"ok": False, "error": str(hl_all)}
    if isinstance(kr_all, Exception):
        kr = {"ok": False, "error": str(kr_all)}

    raw = bn.pop("_raw")

    # Aggregated OI across exchanges (USD)
    oi_parts = []
    for ex in (bn, hl, kr):
        if isinstance(ex, dict) and ex.get("ok") and ex.get("oi_usd"):
            oi_parts.append(float(ex["oi_usd"]))
    total_oi_usd = sum(oi_parts) if oi_parts else None

    return {
        "asset": asset,
        "symbol": symbol,
        "ticker": raw["ticker"],
        "klines_4h": k4 if not isinstance(k4, Exception) else [],
        "klines_1d": k1d if not isinstance(k1d, Exception) else [],
        "klines_1h": k1h if not isinstance(k1h, Exception) else [],
        "global_ls": raw["global_ls"],
        "top_account_ls": raw["top_account_ls"],
        "top_position_ls": raw["top_position_ls"],
        "taker_ls": raw["taker_ls"],
        "open_interest": raw["open_interest"],
        "funding": raw["funding"],
        "exchanges": {
            "binance": bn,
            "hyperliquid": hl,
            "kraken": kr,
        },
        "total_oi_usd": total_oi_usd,
    }
