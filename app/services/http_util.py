"""Shared HTTP helpers: 429 retry, light rate limiting."""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

# Cap concurrent outbound market calls (Binance is strict on shared cloud IPs)
_SEM = asyncio.Semaphore(4)


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    params: dict | None = None,
    *,
    retries: int = 3,
    label: str = "",
) -> Any:
    """
    GET JSON with 429/5xx retry + jitter.
    Raises httpx.HTTPStatusError after retries exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        async with _SEM:
            try:
                r = await client.get(url, params=params or {})
            except httpx.TransportError as e:
                last_exc = e
                if attempt >= retries:
                    raise
                await asyncio.sleep(0.4 * (2**attempt) + random.uniform(0, 0.3))
                continue

        if r.status_code == 429 or r.status_code >= 500:
            last_exc = httpx.HTTPStatusError(
                f"HTTP {r.status_code} {label or url}",
                request=r.request,
                response=r,
            )
            if attempt >= retries:
                r.raise_for_status()
            # Retry-After header if present
            ra = r.headers.get("Retry-After")
            if ra and ra.isdigit():
                wait = min(float(ra), 8.0)
            else:
                wait = 0.6 * (2**attempt) + random.uniform(0.1, 0.5)
            await asyncio.sleep(wait)
            continue

        r.raise_for_status()
        return r.json()

    if last_exc:
        raise last_exc
    raise RuntimeError(f"get_json failed: {label or url}")


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    body: dict,
    *,
    retries: int = 2,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        async with _SEM:
            try:
                r = await client.post(url, json=body)
            except httpx.TransportError as e:
                last_exc = e
                if attempt >= retries:
                    raise
                await asyncio.sleep(0.4 * (2**attempt))
                continue

        if r.status_code == 429 or r.status_code >= 500:
            if attempt >= retries:
                r.raise_for_status()
            await asyncio.sleep(0.5 * (2**attempt) + random.uniform(0, 0.3))
            continue

        r.raise_for_status()
        return r.json()

    if last_exc:
        raise last_exc
    raise RuntimeError(f"post_json failed: {url}")
