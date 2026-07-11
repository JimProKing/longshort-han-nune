"""Technical analysis: support/resistance, ATR, pivots, sentiment score."""

from __future__ import annotations

from statistics import mean
from typing import Any


def _closes(klines: list[dict]) -> list[float]:
    return [float(k["close"]) for k in klines]


def _highs(klines: list[dict]) -> list[float]:
    return [float(k["high"]) for k in klines]


def _lows(klines: list[dict]) -> list[float]:
    return [float(k["low"]) for k in klines]


def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return float(values[-1])
    alpha = 2 / (period + 1)
    e = float(values[0])
    for v in values[1:]:
        e = alpha * float(v) + (1 - alpha) * e
    return e


def sma(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    window = values[-period:] if len(values) >= period else values
    return float(mean(window))


def atr(klines: list[dict], period: int = 14) -> float:
    if len(klines) < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(klines)):
        h = klines[i]["high"]
        l = klines[i]["low"]
        prev_c = klines[i - 1]["close"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    if not trs:
        return 0.0
    window = trs[-period:] if len(trs) >= period else trs
    return float(mean(window))


def classic_pivots(high: float, low: float, close: float) -> dict[str, float]:
    p = (high + low + close) / 3
    r1 = 2 * p - low
    s1 = 2 * p - high
    r2 = p + (high - low)
    s2 = p - (high - low)
    r3 = high + 2 * (p - low)
    s3 = low - 2 * (high - p)
    return {
        "pivot": p,
        "r1": r1,
        "r2": r2,
        "r3": r3,
        "s1": s1,
        "s2": s2,
        "s3": s3,
    }


def fibonacci_levels(swing_high: float, swing_low: float) -> dict[str, float]:
    diff = swing_high - swing_low
    return {
        "0.0": swing_high,
        "0.236": swing_high - 0.236 * diff,
        "0.382": swing_high - 0.382 * diff,
        "0.5": swing_high - 0.5 * diff,
        "0.618": swing_high - 0.618 * diff,
        "0.786": swing_high - 0.786 * diff,
        "1.0": swing_low,
    }


def find_swing_levels(
    klines: list[dict], lookback: int = 5, max_levels: int = 6
) -> tuple[list[float], list[float]]:
    """Local swing highs / lows as potential resistance / support."""
    highs = _highs(klines)
    lows = _lows(klines)
    n = len(klines)
    swing_highs: list[float] = []
    swing_lows: list[float] = []

    for i in range(lookback, n - lookback):
        window_h = highs[i - lookback : i + lookback + 1]
        window_l = lows[i - lookback : i + lookback + 1]
        if highs[i] == max(window_h):
            swing_highs.append(float(highs[i]))
        if lows[i] == min(window_l):
            swing_lows.append(float(lows[i]))

    def cluster(levels: list[float], tol_pct: float = 0.003) -> list[float]:
        if not levels:
            return []
        levels = sorted(levels)
        clusters: list[list[float]] = [[levels[0]]]
        for lv in levels[1:]:
            if abs(lv - clusters[-1][-1]) / clusters[-1][-1] <= tol_pct:
                clusters[-1].append(lv)
            else:
                clusters.append([lv])
        return [float(mean(c)) for c in clusters]

    supports = cluster(swing_lows)[-max_levels:]
    resistances = cluster(swing_highs)[-max_levels:]
    return supports, resistances


def sentiment_from_ratios(
    global_ls: list[dict],
    top_account: list[dict],
    top_position: list[dict],
    taker: list[dict],
    funding_rate: float,
) -> dict[str, Any]:
    """
    Composite market sentiment.
    High retail long ratio + negative funding often = crowded long (risk of dump).
    """
    g = global_ls[-1] if global_ls else None
    ta = top_account[-1] if top_account else None
    tp = top_position[-1] if top_position else None
    tk = taker[-1] if taker else None

    global_long_pct = (g["long_account"] * 100) if g else 50.0
    global_short_pct = (g["short_account"] * 100) if g else 50.0
    global_ratio = g["long_short_ratio"] if g else 1.0

    top_acc_long = (ta["long_account"] * 100) if ta else 50.0
    top_acc_ratio = ta["long_short_ratio"] if ta else 1.0

    top_pos_long = (tp["long_account"] * 100) if tp else 50.0
    top_pos_ratio = tp["long_short_ratio"] if tp else 1.0

    taker_ratio = tk["buy_sell_ratio"] if tk else 1.0

    retail_bias = (global_long_pct - 50) * 2
    whale_bias = (top_pos_long - 50) * 2
    flow_bias = (taker_ratio - 1.0) * 50
    funding_bias = funding_rate * 10000

    ratio_trend = 0.0
    if len(global_ls) >= 12:
        recent = mean([x["long_short_ratio"] for x in global_ls[-6:]])
        prev = mean([x["long_short_ratio"] for x in global_ls[-12:-6]])
        ratio_trend = float(recent - prev)

    composite = (
        0.25 * retail_bias
        + 0.30 * whale_bias
        + 0.25 * flow_bias
        + 0.10 * funding_bias * 10
        + 0.10 * (ratio_trend * 50)
    )
    composite = float(max(-100, min(100, composite)))

    if composite >= 25:
        label = "롱 우세 (강세 편향)"
        bias = "bullish"
    elif composite <= -25:
        label = "숏 우세 (약세 편향)"
        bias = "bearish"
    else:
        label = "중립 / 혼조"
        bias = "neutral"

    crowded_long = global_long_pct >= 58 and funding_rate > 0.00005
    crowded_short = global_short_pct >= 58 and funding_rate < -0.00005

    return {
        "global_long_pct": round(global_long_pct, 2),
        "global_short_pct": round(global_short_pct, 2),
        "global_ls_ratio": round(global_ratio, 4),
        "top_account_long_pct": round(top_acc_long, 2),
        "top_account_ls_ratio": round(top_acc_ratio, 4),
        "top_position_long_pct": round(top_pos_long, 2),
        "top_position_ls_ratio": round(top_pos_ratio, 4),
        "taker_buy_sell_ratio": round(taker_ratio, 4),
        "funding_rate": funding_rate,
        "funding_rate_pct": round(funding_rate * 100, 4),
        "composite_score": round(composite, 1),
        "label": label,
        "bias": bias,
        "crowded_long": crowded_long,
        "crowded_short": crowded_short,
        "ratio_trend": round(ratio_trend, 4),
        "history": {
            "global_ls": [
                {
                    "t": x["timestamp"],
                    "ratio": round(x["long_short_ratio"], 4),
                    "long_pct": round(x["long_account"] * 100, 2),
                }
                for x in global_ls
            ],
            "taker": [
                {
                    "t": x["timestamp"],
                    "ratio": round(x["buy_sell_ratio"], 4),
                }
                for x in taker
            ],
        },
    }


def build_support_resistance(klines_4h: list[dict], klines_1d: list[dict], price: float) -> dict:
    if not klines_1d or not klines_4h:
        return {"supports": [], "resistances": [], "pivots": {}, "fib": {}, "emas": {}}

    last_day = klines_1d[-2] if len(klines_1d) >= 2 else klines_1d[-1]
    pivots = classic_pivots(last_day["high"], last_day["low"], last_day["close"])

    swing_s, swing_r = find_swing_levels(klines_4h, lookback=4, max_levels=8)
    d_s, d_r = find_swing_levels(klines_1d, lookback=3, max_levels=5)

    recent = klines_1d[-30:] if len(klines_1d) >= 30 else klines_1d
    sh = max(k["high"] for k in recent)
    sl = min(k["low"] for k in recent)
    fib = fibonacci_levels(sh, sl)

    closes_4h = _closes(klines_4h)
    emas = {
        "ema20": round(ema(closes_4h, 20), 6),
        "ema50": round(ema(closes_4h, 50), 6),
        "ema200": round(ema(closes_4h, 200), 6),
        "sma20": round(sma(closes_4h, 20), 6),
    }

    support_candidates = (
        swing_s
        + d_s
        + [pivots["s1"], pivots["s2"], pivots["s3"], pivots["pivot"]]
        + [fib["0.618"], fib["0.786"], fib["0.5"], fib["1.0"]]
        + [emas["ema20"], emas["ema50"], emas["ema200"]]
    )
    resistance_candidates = (
        swing_r
        + d_r
        + [pivots["r1"], pivots["r2"], pivots["r3"], pivots["pivot"]]
        + [fib["0.0"], fib["0.236"], fib["0.382"], fib["0.5"]]
        + [emas["ema20"], emas["ema50"], emas["ema200"]]
    )

    def unique_sorted(levels: list[float], below: bool) -> list[dict]:
        filtered = [lv for lv in levels if (lv < price if below else lv > price) and lv > 0]
        filtered = sorted(set(round(lv, 8) for lv in filtered), reverse=below)
        out: list[float] = []
        for lv in filtered:
            if not out or abs(lv - out[-1]) / price > 0.0025:
                out.append(lv)
        result = []
        for lv in out[:6]:
            dist = (lv - price) / price * 100
            strength = "major" if abs(dist) > 1.5 else "near"
            major_refs = [
                pivots["s1"],
                pivots["s2"],
                pivots["r1"],
                pivots["r2"],
                emas["ema50"],
                emas["ema200"],
                fib["0.618"],
                fib["0.5"],
            ]
            if any(abs(lv - m) / price < 0.004 for m in major_refs):
                strength = "major"
            result.append(
                {
                    "price": round(lv, 6 if price < 10 else 2),
                    "distance_pct": round(dist, 2),
                    "strength": strength,
                }
            )
        return result

    supports = unique_sorted(support_candidates, below=True)
    resistances = unique_sorted(resistance_candidates, below=False)

    return {
        "supports": supports,
        "resistances": resistances,
        "pivots": {k: round(v, 6 if price < 10 else 2) for k, v in pivots.items()},
        "fib": {k: round(v, 6 if price < 10 else 2) for k, v in fib.items()},
        "emas": emas,
        "range_high": round(sh, 6 if price < 10 else 2),
        "range_low": round(sl, 6 if price < 10 else 2),
        "atr_4h": round(atr(klines_4h, 14), 6 if price < 10 else 2),
        "atr_1d": round(atr(klines_1d, 14), 6 if price < 10 else 2),
    }


def _round_money(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 2)


def _sanitize_exchange(ex: dict | None) -> dict | None:
    if not ex:
        return {"ok": False, "error": "no data"}
    if not ex.get("ok"):
        return {"ok": False, "error": ex.get("error", "failed")}

    out = {k: v for k, v in ex.items() if not k.startswith("_")}
    for key in (
        "oi_usd",
        "volume_24h_usd",
        "long_notional_usd",
        "short_notional_usd",
        "pos_long_notional_usd",
        "pos_short_notional_usd",
        "taker_buy_usd",
        "taker_sell_usd",
        "mark_price",
        "price",
    ):
        if key in out and out[key] is not None:
            out[key] = _round_money(out[key])
    for key in (
        "global_long_pct",
        "global_short_pct",
        "top_position_long_pct",
        "top_position_short_pct",
        "top_account_long_pct",
        "funding_rate",
        "oi_base",
    ):
        if key in out and out[key] is not None:
            out[key] = round(float(out[key]), 6 if abs(float(out[key])) < 1 else 4)
    return out


def analyze_symbol(bundle: dict) -> dict:
    price = bundle["ticker"]["price"]
    funding = bundle["funding"]["last_funding_rate"]

    sentiment = sentiment_from_ratios(
        bundle["global_ls"],
        bundle["top_account_ls"],
        bundle["top_position_ls"],
        bundle["taker_ls"],
        funding,
    )
    levels = build_support_resistance(bundle["klines_4h"], bundle["klines_1d"], price)

    exchanges = bundle.get("exchanges") or {}
    bn = _sanitize_exchange(exchanges.get("binance"))
    bb = _sanitize_exchange(exchanges.get("bybit"))
    hl = _sanitize_exchange(exchanges.get("hyperliquid"))
    kr = _sanitize_exchange(exchanges.get("kraken"))

    # Enrich sentiment with notional amounts (primary exchange)
    primary = None
    if bn and bn.get("ok"):
        primary = bn
    elif bb and bb.get("ok"):
        primary = bb

    if primary:
        sentiment["oi_usd"] = primary.get("oi_usd")
        sentiment["long_notional_usd"] = primary.get("long_notional_usd")
        sentiment["short_notional_usd"] = primary.get("short_notional_usd")
        sentiment["pos_long_notional_usd"] = primary.get("pos_long_notional_usd")
        sentiment["pos_short_notional_usd"] = primary.get("pos_short_notional_usd")
        sentiment["taker_buy_usd"] = primary.get("taker_buy_usd")
        sentiment["taker_sell_usd"] = primary.get("taker_sell_usd")
        sentiment["volume_24h_usd"] = primary.get("volume_24h_usd")
        sentiment["notional_note"] = primary.get("notional_note")
        sentiment["ls_source"] = primary.get("exchange")

    return {
        "symbol": bundle["symbol"],
        "price": price,
        "change_24h_pct": bundle["ticker"]["change_pct"],
        "high_24h": bundle["ticker"]["high"],
        "low_24h": bundle["ticker"]["low"],
        "volume_24h": bundle["ticker"]["volume"],
        "quote_volume_24h": bundle["ticker"]["quote_volume"],
        "open_interest": bundle["open_interest"]["open_interest"],
        "open_interest_usd": (primary or {}).get("oi_usd"),
        "mark_price": bundle["funding"]["mark_price"],
        "primary_source": bundle.get("primary_source"),
        "sentiment": sentiment,
        "levels": levels,
        "exchanges": {
            "binance": bn,
            "bybit": bb,
            "hyperliquid": hl,
            "kraken": kr,
        },
        "total_oi_usd": _round_money(bundle.get("total_oi_usd")),
        "klines_1h_spark": [
            {"t": k["open_time"], "c": k["close"]} for k in bundle["klines_1h"][-48:]
        ],
    }
