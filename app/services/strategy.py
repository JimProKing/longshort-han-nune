"""Long / Short strategy suggestions: entry, SL, TP."""

from __future__ import annotations

from typing import Any


def _round_price(price: float, ref: float) -> float:
    if ref >= 1000:
        return round(price, 0)  # KRW equities etc.
    if ref >= 100:
        return round(price, 2)
    if ref >= 1:
        return round(price, 4)
    return round(price, 5)


def _rr(entry: float, sl: float, tp: float, side: str) -> float:
    if side == "long":
        risk = entry - sl
        reward = tp - entry
    else:
        risk = sl - entry
        reward = entry - tp
    if risk <= 0:
        return 0.0
    return round(reward / risk, 2)


def _pick_support(supports: list[dict], idx: int = 0) -> float | None:
    if not supports or idx >= len(supports):
        return None
    return float(supports[idx]["price"])


def _pick_resistance(resistances: list[dict], idx: int = 0) -> float | None:
    if not resistances or idx >= len(resistances):
        return None
    return float(resistances[idx]["price"])


def build_long_strategy(analysis: dict) -> dict[str, Any]:
    price = float(analysis["price"])
    levels = analysis["levels"]
    atr = float(levels.get("atr_4h") or price * 0.01)
    supports = levels.get("supports") or []
    resistances = levels.get("resistances") or []
    pivots = levels.get("pivots") or {}
    sentiment = analysis["sentiment"]

    s1 = _pick_support(supports, 0)
    s2 = _pick_support(supports, 1)
    r1 = _pick_resistance(resistances, 0)
    r2 = _pick_resistance(resistances, 1)

    # Entry: pullback to nearest support or slight discount from market
    if s1 and (price - s1) / price < 0.025:
        entry = s1
        entry_type = "지지선 근처 풀백 진입"
    elif pivots.get("s1") and pivots["s1"] < price:
        entry = float(pivots["s1"])
        entry_type = "피봇 S1 풀백 진입"
    else:
        entry = price * 0.995
        entry_type = "현재가 소폭 할인 지정가"

    # SL below next support or 1.5 ATR
    if s2 and s2 < entry:
        sl = s2 - atr * 0.15
        sl_note = "2차 지지 하단 이탈 시 손절"
    elif s1 and s1 < entry:
        sl = s1 - atr * 0.35
        sl_note = "1차 지지 + ATR 버퍼 손절"
    else:
        sl = entry - atr * 1.5
        sl_note = "ATR(4h) × 1.5 손절"

    # TPs
    tp1 = r1 if r1 and r1 > entry else entry + atr * 1.2
    tp2 = r2 if r2 and r2 > entry else entry + atr * 2.2
    if pivots.get("r1") and pivots["r1"] > entry:
        tp1 = min(tp1, float(pivots["r1"])) if r1 else float(pivots["r1"])
    if pivots.get("r2") and pivots["r2"] > entry:
        tp2 = max(tp2, float(pivots["r2"]))

    # Sanity: SL must be below entry
    if sl >= entry:
        sl = entry - atr * 1.2
    if tp1 <= entry:
        tp1 = entry + atr
    if tp2 <= tp1:
        tp2 = tp1 + atr * 0.8

    conf, reason = _confidence("long", sentiment, analysis)

    return {
        "side": "long",
        "label": "롱 전략",
        "entry": _round_price(entry, price),
        "entry_type": entry_type,
        "stop_loss": _round_price(sl, price),
        "sl_note": sl_note,
        "take_profit_1": _round_price(tp1, price),
        "take_profit_2": _round_price(tp2, price),
        "tp1_note": "1차 저항 / 부분 익절 (50%)",
        "tp2_note": "2차 저항 / 잔량 익절",
        "risk_reward_1": _rr(entry, sl, tp1, "long"),
        "risk_reward_2": _rr(entry, sl, tp2, "long"),
        "invalidation": f"{_round_price(sl, price)} 하방 종가 이탈 시 시나리오 무효",
        "confidence": conf,
        "confidence_label": _conf_label(conf),
        "rationale": reason,
        "position_hint": "리스크 기준 계좌의 0.5~1% 손절폭으로 수량 산정 권장",
    }


def build_short_strategy(analysis: dict) -> dict[str, Any]:
    price = float(analysis["price"])
    levels = analysis["levels"]
    atr = float(levels.get("atr_4h") or price * 0.01)
    supports = levels.get("supports") or []
    resistances = levels.get("resistances") or []
    pivots = levels.get("pivots") or {}
    sentiment = analysis["sentiment"]

    r1 = _pick_resistance(resistances, 0)
    r2 = _pick_resistance(resistances, 1)
    s1 = _pick_support(supports, 0)
    s2 = _pick_support(supports, 1)

    if r1 and (r1 - price) / price < 0.025:
        entry = r1
        entry_type = "저항선 근처 반등 숏 진입"
    elif pivots.get("r1") and pivots["r1"] > price:
        entry = float(pivots["r1"])
        entry_type = "피봇 R1 반등 숏 진입"
    else:
        entry = price * 1.005
        entry_type = "현재가 소폭 프리미엄 지정가"

    if r2 and r2 > entry:
        sl = r2 + atr * 0.15
        sl_note = "2차 저항 상단 돌파 시 손절"
    elif r1 and r1 > entry:
        sl = r1 + atr * 0.35
        sl_note = "1차 저항 + ATR 버퍼 손절"
    else:
        sl = entry + atr * 1.5
        sl_note = "ATR(4h) × 1.5 손절"

    tp1 = s1 if s1 and s1 < entry else entry - atr * 1.2
    tp2 = s2 if s2 and s2 < entry else entry - atr * 2.2
    if pivots.get("s1") and pivots["s1"] < entry:
        tp1 = max(tp1, float(pivots["s1"])) if s1 else float(pivots["s1"])
    if pivots.get("s2") and pivots["s2"] < entry:
        tp2 = min(tp2, float(pivots["s2"]))

    if sl <= entry:
        sl = entry + atr * 1.2
    if tp1 >= entry:
        tp1 = entry - atr
    if tp2 >= tp1:
        tp2 = tp1 - atr * 0.8

    conf, reason = _confidence("short", sentiment, analysis)

    return {
        "side": "short",
        "label": "숏 전략",
        "entry": _round_price(entry, price),
        "entry_type": entry_type,
        "stop_loss": _round_price(sl, price),
        "sl_note": sl_note,
        "take_profit_1": _round_price(tp1, price),
        "take_profit_2": _round_price(tp2, price),
        "tp1_note": "1차 지지 / 부분 익절 (50%)",
        "tp2_note": "2차 지지 / 잔량 익절",
        "risk_reward_1": _rr(entry, sl, tp1, "short"),
        "risk_reward_2": _rr(entry, sl, tp2, "short"),
        "invalidation": f"{_round_price(sl, price)} 상방 종가 돌파 시 시나리오 무효",
        "confidence": conf,
        "confidence_label": _conf_label(conf),
        "rationale": reason,
        "position_hint": "리스크 기준 계좌의 0.5~1% 손절폭으로 수량 산정 권장",
    }


def _conf_label(score: int) -> str:
    if score >= 70:
        return "높음"
    if score >= 50:
        return "보통"
    if score >= 35:
        return "낮음"
    return "매우 낮음"


def _confidence(side: str, sentiment: dict, analysis: dict) -> tuple[int, str]:
    """Heuristic confidence for long vs short setup."""
    score = 50
    reasons: list[str] = []
    bias = sentiment.get("bias", "neutral")
    composite = float(sentiment.get("composite_score") or 0)
    gl_raw = sentiment.get("global_long_pct")
    global_long = float(gl_raw) if gl_raw is not None else 50.0
    fr_raw = sentiment.get("funding_rate")
    funding = float(fr_raw) if fr_raw is not None else 0.0
    has_ls = bool(sentiment.get("ls_available", gl_raw is not None))
    price = float(analysis["price"])
    emas = analysis["levels"].get("emas") or {}
    change = float(analysis.get("change_24h_pct") or 0)
    is_stock = analysis.get("asset_type") == "stock"

    ema20 = emas.get("ema20")
    ema50 = emas.get("ema50")

    if is_stock:
        reasons.append("국내 주식 — 기술 레벨·EMA 기반 (선물 롱/숏 비율 없음)")

    if side == "long":
        if bias == "bullish":
            score += 12
            reasons.append("종합 센티먼트 강세")
        elif bias == "bearish":
            score -= 10
            reasons.append("종합 센티먼트 약세 — 롱 주의")

        if ema20 and price > ema20:
            score += 8
            reasons.append("가격 > EMA20 (단기 상승 구조)")
        elif ema20:
            score -= 6
            reasons.append("가격 < EMA20")

        if ema50 and price > ema50:
            score += 6
            reasons.append("가격 > EMA50")

        # Contrarian: crowded short is good for long
        if sentiment.get("crowded_short"):
            score += 10
            reasons.append("숏 과밀(contrarian 롱 유리)")
        if sentiment.get("crowded_long"):
            score -= 12
            reasons.append("롱 과밀 — 청산 위험")

        if has_ls and funding < -0.00005:
            score += 5
            reasons.append("펀딩 음수 — 숏이 롱에게 지불")
        if has_ls and global_long > 62:
            score -= 8
            reasons.append(f"리테일 롱 비중 과다 ({global_long:.1f}%)")

        if change < -3:
            score += 4
            reasons.append("단기 조정 후 반등 여지")

    else:  # short
        if bias == "bearish":
            score += 12
            reasons.append("종합 센티먼트 약세")
        elif bias == "bullish":
            score -= 10
            reasons.append("종합 센티먼트 강세 — 숏 주의")

        if ema20 and price < ema20:
            score += 8
            reasons.append("가격 < EMA20 (단기 하락 구조)")
        elif ema20:
            score -= 6
            reasons.append("가격 > EMA20")

        if ema50 and price < ema50:
            score += 6
            reasons.append("가격 < EMA50")

        if sentiment.get("crowded_long"):
            score += 10
            reasons.append("롱 과밀(contrarian 숏 유리)")
        if sentiment.get("crowded_short"):
            score -= 12
            reasons.append("숏 과밀 — 숏스퀴즈 위험")

        if has_ls and funding > 0.0001:
            score += 5
            reasons.append("펀딩 과열 — 롱 비용 부담")
        if has_ls and global_long < 40:
            score -= 8
            reasons.append(f"리테일 숏 비중 과다 (롱 {global_long:.1f}%)")

        if change > 3:
            score += 4
            reasons.append("단기 급등 후 되돌림 여지")

    # Whale vs retail divergence (crypto L/S only)
    if has_ls:
        tp_raw = sentiment.get("top_position_long_pct")
        top_pos = float(tp_raw) if tp_raw is not None else global_long
        if side == "long" and top_pos > global_long + 5:
            score += 6
            reasons.append("탑트레이더 포지션이 리테일보다 롱 우세")
        if side == "short" and top_pos < global_long - 5:
            score += 6
            reasons.append("탑트레이더 포지션이 리테일보다 숏 우세")

    score = int(max(15, min(90, score + abs(composite) * 0.05)))
    if not reasons:
        reasons.append("기술적 레벨 기반 기본 시나리오")

    return score, " · ".join(reasons[:5])


def preferred_side(long_s: dict, short_s: dict) -> dict:
    if long_s["confidence"] > short_s["confidence"] + 5:
        side = "long"
        note = "현재 데이터상 롱 시나리오 신뢰도가 상대적으로 높습니다."
    elif short_s["confidence"] > long_s["confidence"] + 5:
        side = "short"
        note = "현재 데이터상 숏 시나리오 신뢰도가 상대적으로 높습니다."
    else:
        side = "neutral"
        note = "롱·숏 신뢰도가 비슷합니다. 관망하거나 작은 사이즈로 양쪽 시나리오를 대비하세요."
    return {"preferred": side, "note": note}


def build_strategies(analysis: dict) -> dict:
    long_s = build_long_strategy(analysis)
    short_s = build_short_strategy(analysis)
    return {
        "long": long_s,
        "short": short_s,
        "preference": preferred_side(long_s, short_s),
        "disclaimer": (
            "코인(Binance/Bybit 공개 선물) · 국내주식(Yahoo/KRX 시세) 기준 참고용 분석입니다. "
            "투자 자문이 아니며, 레버리지·청산·슬리피지·호가 괴리는 본인 책임으로 확인하세요."
        ),
    }
