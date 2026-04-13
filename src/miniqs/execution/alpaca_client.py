from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime, timezone
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from src.miniqs.config.asset import AssetConfig
from src.miniqs.config.alpaca import AlpacaConfig
from src.miniqs.execution.http import AlpacaPaperClient


class AlpacaClient:
	"""Thin Alpaca API client for market data, orders, and positions.

	The client intentionally contains no strategy, risk, or mode logic.
	"""

	def __init__(self, config: AlpacaConfig) -> None:
		self.config = config
		self._http = AlpacaPaperClient(
			config.api_key_id,
			config.api_secret_key,
			config.rest_base_url,
			trading_api_version=config.trading_api_version,
		)

	def _data_base_url(self) -> str:
		return "https://data.alpaca.markets"

	def _headers(self) -> Dict[str, str]:
		return {
			"APCA-API-KEY-ID": self.config.api_key_id,
			"APCA-API-SECRET-KEY": self.config.api_secret_key,
		}

	def _bars_path(self, asset: AssetConfig) -> str:
		return "/v1beta3/crypto/us/bars" if asset.asset_type == "crypto" else "/v2/stocks/bars"

	def get_market_data(
		self,
		asset: AssetConfig,
		*,
		timeframe: str = "1Min",
		limit: int = 500,
		start: Optional[str] = None,
		end: Optional[str] = None,
	) -> List[Dict[str, float | int]]:
		params: Dict[str, str] = {
			"symbols": asset.symbol,
			"timeframe": timeframe,
			"limit": str(max(1, int(limit))),
		}
		if start:
			params["start"] = start
		if end:
			params["end"] = end

		query = urllib.parse.urlencode(params)
		url = f"{self._data_base_url()}{self._bars_path(asset)}?{query}"
		req = urllib.request.Request(url, headers=self._headers(), method="GET")
		with urllib.request.urlopen(req, timeout=60) as resp:
			raw = resp.read().decode("utf-8")
			payload = json.loads(raw) if raw else {}

		bars = payload.get("bars", {})
		rows = bars.get(asset.symbol, []) if isinstance(bars, dict) else []
		out: List[Dict[str, float | int]] = []
		for row in rows:
			if not isinstance(row, dict):
				continue
			ts = row.get("t")
			try:
				if isinstance(ts, str):
					dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
				else:
					dt = datetime.now(timezone.utc)
				ts_ms = int(dt.timestamp() * 1000)
			except Exception:
				ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
			out.append(
				{
					"timestamp": ts_ms,
					"open": float(row.get("o", 0.0) or 0.0),
					"high": float(row.get("h", 0.0) or 0.0),
					"low": float(row.get("l", 0.0) or 0.0),
					"close": float(row.get("c", 0.0) or 0.0),
					"volume": float(row.get("v", 0.0) or 0.0),
				}
			)
		return out

	def place_order(
		self,
		symbol: str,
		qty: float,
		side: str,
		*,
		client_order_id: Optional[str] = None,
	) -> Dict[str, Any]:
		return self._http.submit_market_order(
			symbol,
			qty,
			side,
			client_order_id=client_order_id,
		)

	def get_positions(self) -> List[Dict[str, Any]]:
		payload = self._http.get_positions()
		return payload if isinstance(payload, list) else []

	async def stream_market_data(self, asset: AssetConfig):
		"""Async generator for live market data snapshots.

		This leaves streaming transport concerns to the caller and only produces
		normalized market data rows.
		"""
		from src.miniqs.data.stream import stream_alpaca_ticks

		local_cfg = replace(self.config, symbols=[asset.symbol])
		async for tick in stream_alpaca_ticks(local_cfg):
			yield {
				"timestamp": int(tick.timestamp.timestamp() * 1000),
				"open": float(tick.price),
				"high": float(tick.price),
				"low": float(tick.price),
				"close": float(tick.price),
				"volume": float(tick.volume),
			}

	def subscribe_to_live(self, asset: AssetConfig, callback: Any) -> None:
		async def _run() -> None:
			async for candle in self.stream_market_data(asset):
				callback(candle)

		try:
			asyncio.get_running_loop()
		except RuntimeError:
			asyncio.run(_run())
		else:
			raise RuntimeError("subscribe_to_live() cannot be called from a running event loop; await stream_market_data() instead")