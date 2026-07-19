import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.analysis import analyze_symbol
from app.services.exchanges import fetch_symbol_bundle


async def main():
    for asset in ["BTC", "ETH", "XRP", "ADA", "XLM", "BCH", "ETC", "SAMSUNG", "SKHYNIX", "HYUNDAI"]:
        b = await fetch_symbol_bundle(asset)
        a = analyze_symbol(b)
        s = a["sentiment"]
        print("===", asset, "===")
        print(
            "price",
            a["price"],
            "oi_usd",
            s.get("oi_usd"),
            "long$",
            s.get("long_notional_usd"),
            "short$",
            s.get("short_notional_usd"),
        )
        print("total_oi", a.get("total_oi_usd"))
        for k, v in a["exchanges"].items():
            if v and v.get("ok"):
                print(
                    " ",
                    k,
                    "oi=",
                    v.get("oi_usd"),
                    "funding=",
                    v.get("funding_rate"),
                    "vol=",
                    v.get("volume_24h_usd"),
                    "ls=",
                    v.get("global_long_pct"),
                )
            else:
                print(" ", k, "FAIL", v)


if __name__ == "__main__":
    asyncio.run(main())
