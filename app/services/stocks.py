"""Korean equities via Yahoo Finance public chart API (no L/S ratios)."""

from __future__ import annotations

from typing import Any

import httpx

from app.services.assets import STOCK_SYMBOLS
from app.services.http_util import get_json

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


async def _chart(
    client: httpx.AsyncClient,
    symbol: str,
    *,
    interval: str,
    range_: str,
) -> dict:
    data = await get_json(
        client,
        YAHOO_CHART.format(symbol=symbol),
        {"interval": interval, "range": range_},
        retries=2,
        label=f"yahoo:{symbol}:{interval}",
    )
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        err = (data.get("chart") or {}).get("error")
        raise RuntimeError(f"Yahoo empty chart {symbol}: {err}")
    return result[0]


def _bars_from_chart(chart: dict) -> list[dict]:
    ts = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    out: list[dict] = []
    for i, t in enumerate(ts):
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        c = closes[i] if i < len(closes) else None
        if o is None or h is None or l is None or c is None:
            continue
        ms = int(t) * 1000
        out.append(
            {
                "open_time": ms,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(volumes[i] or 0) if i < len(volumes) else 0.0,
                "close_time": ms,
            }
        )
    return out


def _aggregate_ohlc(bars: list[dict], group_size: int) -> list[dict]:
    """Resample e.g. 1h → 4h by grouping consecutive bars."""
    if group_size <= 1 or not bars:
        return bars
    out: list[dict] = []
    for i in range(0, len(bars), group_size):
        chunk = bars[i : i + group_size]
        if not chunk:
            continue
        out.append(
            {
                "open_time": chunk[0]["open_time"],
                "open": chunk[0]["open"],
                "high": max(b["high"] for b in chunk),
                "low": min(b["low"] for b in chunk),
                "close": chunk[-1]["close"],
                "volume": sum(b["volume"] for b in chunk),
                "close_time": chunk[-1]["close_time"],
            }
        )
    return out


async def fetch_stock_bundle(client: httpx.AsyncClient, asset: str) -> dict[str, Any]:
    """Build analysis-compatible bundle for a KRX stock (no futures L/S)."""
    asset = asset.upper()
    if asset not in STOCK_SYMBOLS:
        raise ValueError(f"Unsupported stock: {asset}")
    symbol = STOCK_SYMBOLS[asset]

    # Reuse headers if client already has them
    h1, d1 = await asyncio_gather_charts(client, symbol)

    klines_1h = _bars_from_chart(h1)
    klines_1d = _bars_from_chart(d1)
    klines_4h = _aggregate_ohlc(klines_1h, 4)

    if not klines_1d and not klines_1h:
        raise RuntimeError(f"{asset} 봉 데이터 없음")

    meta = (h1.get("meta") or d1.get("meta") or {})
    price = float(meta.get("regularMarketPrice") or (klines_1h or klines_1d)[-1]["close"])
    prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
    change_pct = ((price - prev) / prev * 100.0) if prev else 0.0

    # 24h high/low from recent daily or last ~24 1h bars
    day = klines_1d[-1] if klines_1d else None
    if day:
        high_24h = float(day["high"])
        low_24h = float(day["low"])
        vol = float(day["volume"])
    else:
        window = klines_1h[-24:] if len(klines_1h) >= 2 else klines_1h
        high_24h = max(b["high"] for b in window)
        low_24h = min(b["low"] for b in window)
        vol = sum(b["volume"] for b in window)

    volume_krw = vol * price if vol else None

    ticker = {
        "symbol": symbol,
        "price": price,
        "change_pct": change_pct,
        "high": high_24h,
        "low": low_24h,
        "volume": vol,
        "quote_volume": volume_krw or 0.0,
    }

    # Neutral L/S placeholders — equities have no public account long/short ratio here
    empty_ls: list[dict] = []
    empty_taker: list[dict] = []

    primary = {
        "ok": True,
        "exchange": "krx",
        "symbol": symbol,
        "price": price,
        "mark_price": price,
        "change_24h_pct": change_pct,
        "high_24h": high_24h,
        "low_24h": low_24h,
        "volume_24h_base": vol,
        "volume_24h_usd": volume_krw,  # actually KRW notional
        "funding_rate": None,
        "oi_base": None,
        "oi_usd": None,
        "global_long_pct": None,
        "global_short_pct": None,
        "global_ls_ratio": None,
        "top_account_long_pct": None,
        "top_account_ls_ratio": None,
        "top_position_long_pct": None,
        "top_position_short_pct": None,
        "top_position_ls_ratio": None,
        "taker_buy_sell_ratio": None,
        "taker_buy_vol_base": None,
        "taker_sell_vol_base": None,
        "taker_buy_usd": None,
        "taker_sell_usd": None,
        "long_notional_usd": None,
        "short_notional_usd": None,
        "pos_long_notional_usd": None,
        "pos_short_notional_usd": None,
        "notional_note": "국내 주식 — 계정 롱/숏 비율·OI·펀딩 없음 (지지/저항·시나리오만 제공)",
        "currency": "KRW",
        "asset_type": "stock",
    }

    return {
        "asset": asset,
        "symbol": symbol,
        "primary_source": "yahoo",
        "primary_error": None,
        "asset_type": "stock",
        "currency": "KRW",
        "ticker": ticker,
        "klines_4h": klines_4h[-200:] if klines_4h else [],
        "klines_1d": klines_1d[-120:] if klines_1d else [],
        "klines_1h": klines_1h[-100:] if klines_1h else [],
        "global_ls": empty_ls,
        "top_account_ls": empty_ls,
        "top_position_ls": empty_ls,
        "taker_ls": empty_taker,
        "open_interest": {"open_interest": 0.0, "time": 0},
        "funding": {
            "mark_price": price,
            "index_price": price,
            "last_funding_rate": 0.0,
            "next_funding_time": 0,
        },
        "exchanges": {
            "binance": {"ok": False, "error": "주식 — 선물 L/S 미제공"},
            "bybit": {"ok": False, "error": "주식 — 선물 L/S 미제공"},
            "hyperliquid": {"ok": False, "error": "주식 — 미상장"},
            "kraken": {"ok": False, "error": "주식 — 미상장"},
            "krx": primary,
        },
        "total_oi_usd": None,
    }


async def asyncio_gather_charts(client: httpx.AsyncClient, symbol: str):
    import asyncio

    # Ensure UA even if shared client used
    # httpx merges per-request headers
    async def one(interval: str, range_: str):
        return await _chart(client, symbol, interval=interval, range_=range_)

    h1, d1 = await asyncio.gather(
        one("1h", "3mo"),
        one("1d", "1y"),
    )
    return h1, d1
