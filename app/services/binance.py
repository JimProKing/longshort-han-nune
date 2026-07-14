"""Binance USDⓈ-M Futures public market data client."""

from __future__ import annotations

from typing import Any

import httpx

from app.services.http_util import get_json

FAPI = "https://fapi.binance.com"
FUTURES_DATA = "https://fapi.binance.com/futures/data"

SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "XRP": "XRPUSDT",
}

# Public L/S account ratios are time-bucketed. 5m is the finest Binance offers
# (true tick-level long/short % is not exposed on free REST).
LS_PERIOD = "5m"
LS_HISTORY_LIMIT = 72  # 6h of 5m bars

# Reasonable timeouts for Railway / shared hosting
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> Any:
    return await get_json(client, url, params, retries=3, label=url)


async def fetch_ticker(client: httpx.AsyncClient, symbol: str) -> dict:
    data = await _get(client, f"{FAPI}/fapi/v1/ticker/24hr", {"symbol": symbol})
    return {
        "symbol": symbol,
        "price": float(data["lastPrice"]),
        "change_pct": float(data["priceChangePercent"]),
        "high": float(data["highPrice"]),
        "low": float(data["lowPrice"]),
        "volume": float(data["volume"]),
        "quote_volume": float(data["quoteVolume"]),
    }


async def fetch_klines(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str = "4h",
    limit: int = 200,
) -> list[dict]:
    raw = await _get(
        client,
        f"{FAPI}/fapi/v1/klines",
        {"symbol": symbol, "interval": interval, "limit": limit},
    )
    candles = []
    for k in raw:
        candles.append(
            {
                "open_time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": int(k[6]),
            }
        )
    return candles


async def fetch_global_ls_ratio(
    client: httpx.AsyncClient,
    symbol: str,
    period: str = LS_PERIOD,
    limit: int = LS_HISTORY_LIMIT,
) -> list[dict]:
    raw = await _get(
        client,
        f"{FUTURES_DATA}/globalLongShortAccountRatio",
        {"symbol": symbol, "period": period, "limit": limit},
    )
    return [
        {
            "timestamp": int(x["timestamp"]),
            "long_short_ratio": float(x["longShortRatio"]),
            "long_account": float(x["longAccount"]),
            "short_account": float(x["shortAccount"]),
        }
        for x in raw
    ]


async def fetch_top_trader_ls_ratio(
    client: httpx.AsyncClient,
    symbol: str,
    period: str = LS_PERIOD,
    limit: int = LS_HISTORY_LIMIT,
) -> list[dict]:
    raw = await _get(
        client,
        f"{FUTURES_DATA}/topLongShortAccountRatio",
        {"symbol": symbol, "period": period, "limit": limit},
    )
    return [
        {
            "timestamp": int(x["timestamp"]),
            "long_short_ratio": float(x["longShortRatio"]),
            "long_account": float(x["longAccount"]),
            "short_account": float(x["shortAccount"]),
        }
        for x in raw
    ]


async def fetch_top_trader_position_ratio(
    client: httpx.AsyncClient,
    symbol: str,
    period: str = LS_PERIOD,
    limit: int = LS_HISTORY_LIMIT,
) -> list[dict]:
    raw = await _get(
        client,
        f"{FUTURES_DATA}/topLongShortPositionRatio",
        {"symbol": symbol, "period": period, "limit": limit},
    )
    return [
        {
            "timestamp": int(x["timestamp"]),
            "long_short_ratio": float(x["longShortRatio"]),
            "long_account": float(x["longAccount"]),
            "short_account": float(x["shortAccount"]),
        }
        for x in raw
    ]


async def fetch_taker_ls_ratio(
    client: httpx.AsyncClient,
    symbol: str,
    period: str = LS_PERIOD,
    limit: int = LS_HISTORY_LIMIT,
) -> list[dict]:
    raw = await _get(
        client,
        f"{FUTURES_DATA}/takerlongshortRatio",
        {"symbol": symbol, "period": period, "limit": limit},
    )
    return [
        {
            "timestamp": int(x["timestamp"]),
            "buy_sell_ratio": float(x["buySellRatio"]),
            "buy_vol": float(x["buyVol"]),
            "sell_vol": float(x["sellVol"]),
        }
        for x in raw
    ]


async def fetch_open_interest(client: httpx.AsyncClient, symbol: str) -> dict:
    data = await _get(client, f"{FAPI}/fapi/v1/openInterest", {"symbol": symbol})
    return {
        "symbol": symbol,
        "open_interest": float(data["openInterest"]),
        "time": int(data["time"]),
    }


async def fetch_funding_rate(client: httpx.AsyncClient, symbol: str) -> dict:
    data = await _get(client, f"{FAPI}/fapi/v1/premiumIndex", {"symbol": symbol})
    return {
        "symbol": symbol,
        "mark_price": float(data["markPrice"]),
        "index_price": float(data["indexPrice"]),
        "last_funding_rate": float(data["lastFundingRate"]),
        "next_funding_time": int(data["nextFundingTime"]),
    }


async def fetch_symbol_bundle(symbol: str) -> dict:
    """Fetch all market data needed for one perpetual symbol."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        (
            ticker,
            klines_4h,
            klines_1d,
            klines_1h,
            global_ls,
            top_account,
            top_position,
            taker,
            oi,
            funding,
        ) = await asyncio.gather(
            fetch_ticker(client, symbol),
            fetch_klines(client, symbol, "4h", 200),
            fetch_klines(client, symbol, "1d", 120),
            fetch_klines(client, symbol, "1h", 100),
            fetch_global_ls_ratio(client, symbol),
            fetch_top_trader_ls_ratio(client, symbol),
            fetch_top_trader_position_ratio(client, symbol),
            fetch_taker_ls_ratio(client, symbol),
            fetch_open_interest(client, symbol),
            fetch_funding_rate(client, symbol),
        )

    return {
        "symbol": symbol,
        "ticker": ticker,
        "klines_4h": klines_4h,
        "klines_1d": klines_1d,
        "klines_1h": klines_1h,
        "global_ls": global_ls,
        "top_account_ls": top_account,
        "top_position_ls": top_position,
        "taker_ls": taker,
        "open_interest": oi,
        "funding": funding,
    }
