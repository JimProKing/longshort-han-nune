"""OCN weekly TV schedule (from ocn.cjenm.com SSR __NEXT_DATA__)."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

# Fallback: page HTML with embedded Next.js payload (schedule is not a stable public JSON API)
OCN_SCHEDULE_URL = "https://ocn.cjenm.com/ko/ocn-schedule/"
KST = ZoneInfo("Asia/Seoul")

_cache: tuple[float, dict] | None = None
CACHE_TTL_SEC = 600  # schedule rarely changes mid-day


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (compatible; longshort-han-nune/1.0; "
            "+https://github.com/JimProKing/longshort-han-nune)"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }


def _extract_next_data(html: str) -> dict:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    if not m:
        raise RuntimeError("OCN 페이지에서 __NEXT_DATA__ 를 찾지 못했습니다")
    return json.loads(m.group(1))


def _find_schedule_blob(next_data: dict) -> dict:
    fallback = (next_data.get("props") or {}).get("pageProps", {}).get("fallback") or {}
    if not isinstance(fallback, dict):
        raise RuntimeError("OCN fallback 데이터 없음")

    for _key, val in fallback.items():
        if not isinstance(val, dict):
            continue
        data = val.get("data")
        if not isinstance(data, dict):
            continue
        if "schePgmList" in data and "scheDtList" in data:
            return data

    raise RuntimeError("OCN 편성표 모듈(schePgmList)을 찾지 못했습니다")


def _fmt_date_label(sche_dt: str, sche_day: str | None, sche_wkday: str | None) -> str:
    # sche_dt: YYYYMMDD
    try:
        y, m, d = int(sche_dt[:4]), int(sche_dt[4:6]), int(sche_dt[6:8])
        return f"{m}/{d} ({sche_wkday or ''})".strip()
    except Exception:
        return sche_dt


def _normalize_program(p: dict) -> dict[str, Any]:
    start_unix = p.get("bdStrDtm")
    end_unix = p.get("bdEndDtm")
    # timestamps appear to be UTC epoch seconds
    start_iso = None
    end_iso = None
    if start_unix:
        start_iso = datetime.fromtimestamp(int(start_unix), tz=timezone.utc).astimezone(KST).isoformat()
    if end_unix:
        end_iso = datetime.fromtimestamp(int(end_unix), tz=timezone.utc).astimezone(KST).isoformat()

    title = (p.get("pgmNm") or "").strip()
    episode = (p.get("pgmEpinoNm") or "").strip() or None
    # avoid duplicate title/episode display when same
    if episode and episode.replace(" ", "") == title.replace(" ", ""):
        episode = None

    return {
        "id": p.get("scheId"),
        "date": p.get("scheDt"),
        "start_time": p.get("bdStrTtm"),  # HH:MM
        "end_time": p.get("bdEndTtm"),
        "ampm": p.get("bdStrTm"),  # 오전/오후
        "start_unix": int(start_unix) if start_unix else None,
        "end_unix": int(end_unix) if end_unix else None,
        "start_iso": start_iso,
        "end_iso": end_iso,
        "title": title,
        "episode": episode,
        "flag": p.get("bdFgNm"),  # 본/재
        "rating": p.get("dlbrtGrd"),
        "rating_label": p.get("dlbrtGrdNm"),
        "caption": p.get("captnBdYn") == "Y",  # 자막
        "audio_desc": p.get("scrnExplnaBdYn") == "Y",  # 화면해설
        "sign_lang": p.get("slIntprBdYn") == "Y",  # 수어
        "channel": p.get("chnNm") or "OCN",
        "detail_url": p.get("frontDetailUrlAddr"),
    }


def _build_payload(raw: dict) -> dict:
    days_raw = raw.get("scheDtList") or []
    pgms_raw = raw.get("schePgmList") or []

    days = []
    for d in days_raw:
        sche_dt = d.get("scheDt")
        days.append(
            {
                "date": sche_dt,
                "day": d.get("scheDay"),
                "weekday": d.get("scheWkday"),
                "label": _fmt_date_label(sche_dt or "", d.get("scheDay"), d.get("scheWkday")),
            }
        )

    programs = [_normalize_program(p) for p in pgms_raw if p.get("pgmNm")]

    by_date: dict[str, list] = {}
    for p in programs:
        by_date.setdefault(p["date"], []).append(p)

    # sort each day by start time
    for dt, items in by_date.items():
        items.sort(key=lambda x: (x.get("start_unix") or 0, x.get("start_time") or ""))

    now = datetime.now(tz=KST)
    today_key = now.strftime("%Y%m%d")
    now_unix = int(now.timestamp())

    # mark currently airing
    for items in by_date.values():
        for p in items:
            su, eu = p.get("start_unix"), p.get("end_unix")
            p["on_air"] = bool(su and eu and su <= now_unix < eu)

    return {
        "channel": "OCN",
        "source_url": OCN_SCHEDULE_URL,
        "timezone": "Asia/Seoul",
        "today": today_key,
        "now_iso": now.isoformat(),
        "days": days,
        "programs_by_date": by_date,
        "program_count": len(programs),
        "disclaimer": "편성표는 방송사 사정에 따라 변경될 수 있습니다. 출처: OCN 공식 편성표.",
    }


def _refresh_live_flags(payload: dict) -> dict:
    """Update today / on_air without re-fetching."""
    now = datetime.now(tz=KST)
    today_key = now.strftime("%Y%m%d")
    now_unix = int(now.timestamp())
    by_date = payload.get("programs_by_date") or {}
    for items in by_date.values():
        for p in items:
            su, eu = p.get("start_unix"), p.get("end_unix")
            p["on_air"] = bool(su and eu and su <= now_unix < eu)
    return {
        **payload,
        "today": today_key,
        "now_iso": now.isoformat(),
    }


async def fetch_ocn_schedule(
    client: httpx.AsyncClient | None = None,
    *,
    force: bool = False,
) -> dict:
    global _cache
    now = time.time()
    if not force and _cache and now - _cache[0] < CACHE_TTL_SEC:
        data = _refresh_live_flags(_cache[1])
        return {**data, "cached": True, "cache_age_sec": int(now - _cache[0])}

    owns = client is None
    if owns:
        client = httpx.AsyncClient(timeout=20.0, headers=_headers(), follow_redirects=True)
    assert client is not None

    try:
        # Prefer plain GET of HTML (SSR embeds full week schedule)
        r = await client.get(OCN_SCHEDULE_URL, headers=_headers())
        r.raise_for_status()
        next_data = _extract_next_data(r.text)
        blob = _find_schedule_blob(next_data)
        payload = _build_payload(blob)
        payload["cached"] = False
        payload["fetched_at"] = int(now * 1000)
        _cache = (now, payload)
        return payload
    finally:
        if owns:
            await client.aclose()
