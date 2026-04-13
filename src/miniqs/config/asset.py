from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Literal, Optional
from zoneinfo import ZoneInfo


AssetType = Literal["crypto", "equity"]


@dataclass(frozen=True)
class AssetMarketHours:
    open: str
    close: str
    timezone: str = "America/New_York"


@dataclass(frozen=True)
class AssetConfig:
    symbol: str
    asset_type: AssetType
    market_hours: Optional[AssetMarketHours] = None
    trading_fees: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["asset_type"] = str(self.asset_type)
        payload["symbol"] = self.symbol
        return payload


def _normalize_symbol(symbol: str) -> str:
    return str(symbol).strip().upper()


def infer_asset_type(symbol: str) -> AssetType:
    sym = _normalize_symbol(symbol)
    if "/" in sym or sym.startswith("BTC") or sym.startswith("ETH"):
        return "crypto"
    return "equity"


def default_asset_config(symbol: str) -> AssetConfig:
    sym = _normalize_symbol(symbol)
    asset_type = infer_asset_type(sym)
    if asset_type == "crypto":
        return AssetConfig(
            symbol=sym,
            asset_type="crypto",
            market_hours=None,
            trading_fees=0.001,
        )
    return AssetConfig(
        symbol=sym,
        asset_type="equity",
        market_hours=AssetMarketHours(open="09:30", close="16:00", timezone="America/New_York"),
        trading_fees=0.0001,
    )


def resolve_asset_config(
    *,
    symbol: str,
    asset_type: Optional[str] = None,
    market_hours: Optional[Dict[str, str]] = None,
    trading_fees: Optional[float] = None,
) -> AssetConfig:
    base = default_asset_config(symbol)
    resolved_type = str(asset_type or base.asset_type).strip().lower()
    final_type: AssetType = "crypto" if resolved_type == "crypto" else "equity"

    hours_obj: Optional[AssetMarketHours] = base.market_hours if final_type == "equity" else None
    if final_type == "equity" and isinstance(market_hours, dict):
        open_s = str(market_hours.get("open", hours_obj.open if hours_obj else "09:30"))
        close_s = str(market_hours.get("close", hours_obj.close if hours_obj else "16:00"))
        tz_s = str(market_hours.get("timezone", hours_obj.timezone if hours_obj else "America/New_York"))
        hours_obj = AssetMarketHours(open=open_s, close=close_s, timezone=tz_s)

    fees = float(trading_fees) if trading_fees is not None else float(base.trading_fees)
    return AssetConfig(
        symbol=_normalize_symbol(symbol),
        asset_type=final_type,
        market_hours=hours_obj,
        trading_fees=fees,
    )


def is_asset_tradable_now(config: AssetConfig, now_utc: Optional[datetime] = None) -> bool:
    if config.asset_type == "crypto":
        return True
    if config.market_hours is None:
        return True

    now = now_utc or datetime.utcnow()
    if now.tzinfo is None:
        from datetime import timezone

        now = now.replace(tzinfo=timezone.utc)

    local = now.astimezone(ZoneInfo(config.market_hours.timezone))
    if local.weekday() >= 5:
        return False

    open_hour, open_min = [int(x) for x in config.market_hours.open.split(":", 1)]
    close_hour, close_min = [int(x) for x in config.market_hours.close.split(":", 1)]
    hhmm = local.hour * 60 + local.minute
    start = open_hour * 60 + open_min
    end = close_hour * 60 + close_min
    return start <= hhmm < end
