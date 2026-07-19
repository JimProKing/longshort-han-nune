"""Central asset registry — crypto + TradFi stock perpetuals (Binance/Bybit)."""

from __future__ import annotations

from typing import Any, Literal

AssetType = Literal["crypto", "stock"]

# Display order on the site
ASSET_ORDER: list[str] = [
    "BTC",
    "ETH",
    "XRP",
    "ADA",
    "XLM",
    "BCH",
    "ETC",
    "SAMSUNG",
    "SKHYNIX",
    "HYUNDAI",
]

# Crypto USD-M perpetuals
CRYPTO_SYMBOLS: dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "XRP": "XRPUSDT",
    "ADA": "ADAUSDT",
    "XLM": "XLMUSDT",
    "BCH": "BCHUSDT",
    "ETC": "ETCUSDT",
}

# Binance/Bybit TradFi stock-linked perpetuals (USDT, not KRX cash shares)
STOCK_PERP_SYMBOLS: dict[str, str] = {
    "SAMSUNG": "SAMSUNGUSDT",
    "SKHYNIX": "SKHYNIXUSDT",
    "HYUNDAI": "HYUNDAIUSDT",
}

# All assets that use the Binance/Bybit L/S pipeline
PERP_SYMBOLS: dict[str, str] = {**CRYPTO_SYMBOLS, **STOCK_PERP_SYMBOLS}

# Hyperliquid coin names (crypto only)
HL_COINS: dict[str, str] = {
    "BTC": "BTC",
    "ETH": "ETH",
    "XRP": "XRP",
    "ADA": "ADA",
    "XLM": "XLM",
    "BCH": "BCH",
    "ETC": "ETC",
}

# Kraken Futures perpetual symbols (crypto only)
KRAKEN_SYMBOLS: dict[str, str] = {
    "BTC": "PF_XBTUSD",
    "ETH": "PF_ETHUSD",
    "XRP": "PF_XRPUSD",
    "ADA": "PF_ADAUSD",
    "XLM": "PF_XLMUSD",
    "BCH": "PF_BCHUSD",
    "ETC": "PF_ETCUSD",
}

# Optional KRX reference tickers (Yahoo) — not used for L/S
STOCK_KRX_SYMBOLS: dict[str, str] = {
    "SAMSUNG": "005930.KS",
    "SKHYNIX": "000660.KS",
    "HYUNDAI": "005380.KS",
}

# Backward-compatible alias
STOCK_SYMBOLS = STOCK_KRX_SYMBOLS

ASSET_META: dict[str, dict[str, Any]] = {
    "BTC": {
        "type": "crypto",
        "name": "Bitcoin",
        "name_ko": "비트코인",
        "currency": "USD",
        "color": "#f7931a",
        "cls": "btc",
    },
    "ETH": {
        "type": "crypto",
        "name": "Ethereum",
        "name_ko": "이더리움",
        "currency": "USD",
        "color": "#627eea",
        "cls": "eth",
    },
    "XRP": {
        "type": "crypto",
        "name": "XRP",
        "name_ko": "리플",
        "currency": "USD",
        "color": "#00aae4",
        "cls": "xrp",
    },
    "ADA": {
        "type": "crypto",
        "name": "Cardano",
        "name_ko": "에이다",
        "currency": "USD",
        "color": "#0033ad",
        "cls": "ada",
    },
    "XLM": {
        "type": "crypto",
        "name": "Stellar",
        "name_ko": "스텔라루멘",
        "currency": "USD",
        "color": "#14b6e7",
        "cls": "xlm",
    },
    "BCH": {
        "type": "crypto",
        "name": "Bitcoin Cash",
        "name_ko": "비트코인캐시",
        "currency": "USD",
        "color": "#8dc351",
        "cls": "bch",
    },
    "ETC": {
        "type": "crypto",
        "name": "Ethereum Classic",
        "name_ko": "이더리움클래식",
        "currency": "USD",
        "color": "#328332",
        "cls": "etc",
    },
    "SAMSUNG": {
        "type": "stock",
        "name": "Samsung Electronics",
        "name_ko": "삼성전자",
        "currency": "USD",
        "color": "#1428a0",
        "cls": "samsung",
        "exchange": "Binance TradFi",
        "note": "Binance/Bybit SAMSUNGUSDT 무기한 (KRX 현물 아님)",
    },
    "SKHYNIX": {
        "type": "stock",
        "name": "SK hynix",
        "name_ko": "SK하이닉스",
        "currency": "USD",
        "color": "#ea002c",
        "cls": "skhynix",
        "exchange": "Binance TradFi",
        "note": "Binance/Bybit SKHYNIXUSDT 무기한 (KRX 현물 아님)",
    },
    "HYUNDAI": {
        "type": "stock",
        "name": "Hyundai Motor",
        "name_ko": "현대차",
        "currency": "USD",
        "color": "#002c5f",
        "cls": "hyundai",
        "exchange": "Binance TradFi",
        "note": "Binance/Bybit HYUNDAIUSDT 무기한 (KRX 현물 아님)",
    },
}


def asset_type(asset: str) -> AssetType:
    meta = ASSET_META.get(asset.upper())
    if not meta:
        raise KeyError(f"Unknown asset: {asset}")
    return meta["type"]


def is_crypto(asset: str) -> bool:
    return asset_type(asset) == "crypto"


def is_stock(asset: str) -> bool:
    return asset_type(asset) == "stock"


def is_perp(asset: str) -> bool:
    """True if asset has Binance/Bybit USDT perpetual (crypto or TradFi stock)."""
    return asset.upper() in PERP_SYMBOLS


def perp_symbol(asset: str) -> str:
    return PERP_SYMBOLS[asset.upper()]


def crypto_symbol(asset: str) -> str:
    return CRYPTO_SYMBOLS[asset.upper()]


def stock_symbol(asset: str) -> str:
    """KRX Yahoo ticker (reference only)."""
    return STOCK_KRX_SYMBOLS[asset.upper()]


def display_symbol(asset: str) -> str:
    a = asset.upper()
    if a in PERP_SYMBOLS:
        return PERP_SYMBOLS[a]
    return a


def known_assets() -> list[str]:
    return list(ASSET_ORDER)


def assert_known(asset: str) -> str:
    a = asset.upper()
    if a not in ASSET_META:
        raise KeyError(a)
    return a
