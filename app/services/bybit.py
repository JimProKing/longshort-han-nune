"""Bybit linear perpetual public market data (Binance fallback for restricted IPs)."""

from __future__ import annotations

from typing import Any

import httpx

from app.services.http_util import get_json

BYBIT = "https://api.bybit.com"

SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "XRP": "XRPUSDT",
}

# Bybit kline interval strings
INTERVAL_MAP = {
    "1h": "60",
    "4h": "240",
    "1d": "D",
}


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> Any:
    data = await get_json(client, f"{BYBIT}{path}", params, retries=2, label=path)
    if data.get("retCode") not in (0, "0", None):
        raise RuntimeError(f"Bybit {path}: {data.get('retMsg', data)}")
    return data.get("result") or {}


async def fetch_ticker(client: httpx.AsyncClient, symbol: str) -> dict:
    result = await _get(
        client,
        "/v5/market/tickers",
        {"category": "linear", "symbol": symbol},
    )
    rows = result.get("list") or []
    if not rows:
        raise RuntimeError(f"Bybit ticker empty: {symbol}")
    t = rows[0]
    last = float(t["lastPrice"])
    prev = float(t.get("prevPrice24h") or last)
    change_pct = float(t.get("price24hPcnt") or 0) * 100
    return {
        "symbol": symbol,
        "price": last,
        "change_pct": change_pct,
        "high": float(t.get("highPrice24h") or last),
        "low": float(t.get("lowPrice24h") or last),
        "volume": float(t.get("volume24h") or 0),
        "quote_volume": float(t.get("turnover24h") or 0),
        "mark_price": float(t.get("markPrice") or last),
        "index_price": float(t.get("indexPrice") or last),
        "funding_rate": float(t.get("fundingRate") or 0),
        "open_interest": float(t.get("openInterest") or 0),
        "open_interest_value": float(t.get("openInterestValue") or 0),
    }


async def fetch_klines(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str = "4h",
    limit: int = 200,
) -> list[dict]:
    bybit_interval = INTERVAL_MAP.get(interval, interval)
    result = await _get(
        client,
        "/v5/market/kline",
        {
            "category": "linear",
            "symbol": symbol,
            "interval": bybit_interval,
            "limit": min(limit, 1000),
        },
    )
    # Bybit returns newest first
    raw = list(reversed(result.get("list") or []))
    candles = []
    for k in raw:
        # [start, open, high, low, close, volume, turnover]
        candles.append(
            {
                "open_time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": int(k[0]),
            }
        )
    return candles


async def fetch_account_ratio(
    client: httpx.AsyncClient, symbol: str, period: str = "1h", limit: int = 24
) -> list[dict]:
    result = await _get(
        client,
        "/v5/market/account-ratio",
        {
            "category": "linear",
            "symbol": symbol,
            "period": period,
            "limit": limit,
        },
    )
    rows = list(reversed(result.get("list") or []))
    out = []
    for x in rows:
        long_a = float(x["buyRatio"])
        short_a = float(x["sellRatio"])
        ratio = (long_a / short_a) if short_a > 0 else long_a
        out.append(
            {
                "timestamp": int(x["timestamp"]),
                "long_short_ratio": ratio,
                "long_account": long_a,
                "short_account": short_a,
            }
        )
    return out


async def fetch_open_interest(client: httpx.AsyncClient, symbol: str) -> dict:
    result = await _get(
        client,
        "/v5/market/open-interest",
        {
            "category": "linear",
            "symbol": symbol,
            "intervalTime": "5min",
            "limit": 1,
        },
    )
    rows = result.get("list") or []
    if not rows:
        return {"open_interest": 0.0, "time": 0}
    row = rows[0]
    return {
        "open_interest": float(row["openInterest"]),
        "time": int(row["timestamp"]),
    }


async def fetch_primary_slice(client: httpx.AsyncClient, asset: str, symbol: str) -> dict:
    """Full primary market slice in Binance-compatible shape (from Bybit)."""
    import asyncio

    ticker, k4, k1d, k1h, ratios, oi = await asyncio.gather(
        fetch_ticker(client, symbol),
        fetch_klines(client, symbol, "4h", 200),
        fetch_klines(client, symbol, "1d", 120),
        fetch_klines(client, symbol, "1h", 100),
        fetch_account_ratio(client, symbol, "1h", 24),
        fetch_open_interest(client, symbol),
    )

    long_pct = (ratios[-1]["long_account"] * 100) if ratios else 50.0
    short_pct = (ratios[-1]["short_account"] * 100) if ratios else 50.0
    oi_usd = ticker.get("open_interest_value") or (
        oi["open_interest"] * ticker["price"] if ticker["price"] else None
    )
    oi_base = ticker.get("open_interest") or oi["open_interest"]

    long_n = oi_usd * (long_pct / 100.0) if oi_usd else None
    short_n = oi_usd * (short_pct / 100.0) if oi_usd else None

    funding = ticker["funding_rate"]

    return {
        "ok": True,
        "exchange": "bybit",
        "symbol": symbol,
        "price": ticker["price"],
        "mark_price": ticker["mark_price"],
        "change_24h_pct": ticker["change_pct"],
        "high_24h": ticker["high"],
        "low_24h": ticker["low"],
        "volume_24h_base": ticker["volume"],
        "volume_24h_usd": ticker["quote_volume"],
        "funding_rate": funding,
        "oi_base": oi_base,
        "oi_usd": oi_usd,
        "global_long_pct": long_pct,
        "global_short_pct": short_pct,
        "global_ls_ratio": ratios[-1]["long_short_ratio"] if ratios else 1.0,
        "top_account_long_pct": long_pct,
        "top_account_ls_ratio": ratios[-1]["long_short_ratio"] if ratios else 1.0,
        "top_position_long_pct": long_pct,
        "top_position_short_pct": short_pct,
        "top_position_ls_ratio": ratios[-1]["long_short_ratio"] if ratios else 1.0,
        "taker_buy_sell_ratio": None,
        "taker_buy_vol_base": None,
        "taker_sell_vol_base": None,
        "taker_buy_usd": None,
        "taker_sell_usd": None,
        "long_notional_usd": long_n,
        "short_notional_usd": short_n,
        "pos_long_notional_usd": long_n,
        "pos_short_notional_usd": short_n,
        "notional_note": "OI × Bybit 계정 롱/숏 비율 추정",
        "_raw": {
            "ticker": {
                "symbol": symbol,
                "price": ticker["price"],
                "change_pct": ticker["change_pct"],
                "high": ticker["high"],
                "low": ticker["low"],
                "volume": ticker["volume"],
                "quote_volume": ticker["quote_volume"],
            },
            "global_ls": ratios,
            "top_account_ls": ratios,
            "top_position_ls": ratios,
            "taker_ls": [],
            "open_interest": {
                "symbol": symbol,
                "open_interest": oi_base,
                "time": oi["time"],
            },
            "funding": {
                "symbol": symbol,
                "mark_price": ticker["mark_price"],
                "index_price": ticker["index_price"],
                "last_funding_rate": funding,
                "next_funding_time": 0,
            },
            "klines_4h": k4,
            "klines_1d": k1d,
            "klines_1h": k1h,
        },
    }
