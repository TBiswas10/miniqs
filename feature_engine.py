"""Feature engineering for tick data.

This module converts incoming ticks into rolling features used by strategies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Dict, Optional, Union
from collections import deque

import numpy as np
import pandas as pd

from data_feed import Tick


@dataclass(frozen=True)
class FeatureSnapshot:
	"""Point-in-time features for a symbol.

	Inputs:
	- symbol, timestamp, price from latest tick
	- rolling windows from recent price history

	Outputs:
	- rolling_mean
	- rolling_volatility (std of returns)
	- momentum (price change over momentum_window)
	"""

	symbol: str
	timestamp: datetime
	price: float
	rolling_mean: float
	rolling_volatility: float
	momentum: float
	realized_vol_short: float
	realized_vol_long: float
	spread_bps: float
	book_imbalance: float
	rel_volume: float
	volume_zscore: float
	trend_slope_short: float
	trend_slope_long: float
	distance_to_ma50: float


class FeatureEngine:
	"""Stateful feature calculator over incoming ticks."""

	def __init__(
		self,
		ma_window: int = 20,
		long_ma_window: int = 50,
		vol_window: int = 20,
		momentum_window: int = 10,
		debug: bool = True,
	) -> None:
		if ma_window < 2 or long_ma_window < 2 or vol_window < 2 or momentum_window < 1:
			raise ValueError(
				"Invalid window sizes: require short/long ma >= 2, vol >= 2, momentum >= 1"
			)

		self.ma_window = ma_window
		self.long_ma_window = long_ma_window
		self.vol_window = vol_window
		self.momentum_window = momentum_window
		self.debug = debug
		history_len = max(
			ma_window + 1,
			long_ma_window + 1,
			vol_window + 1,
			momentum_window + 1,
		)
		self._prices: Deque[float] = deque(maxlen=history_len)
		self._volumes: Deque[float] = deque(maxlen=history_len)
		self._latest_features: Optional[Dict[str, float]] = None

	def update_features(self, new_tick: Union[Tick, Dict[str, object]]) -> Optional[Dict[str, float]]:
		"""Update feature state with a new tick and return latest feature vector.

		Input:
		- new_tick: Tick or dict with keys {timestamp, mid_price}

		Output:
		- feature vector dict with keys:
		  rolling_avg_20, rolling_avg_50, volatility, momentum
		- returns None if history is insufficient
		"""
		if isinstance(new_tick, Tick):
			price = float(new_tick.price)
			volume = float(new_tick.volume)
		else:
			price = float(new_tick["mid_price"])
			volume = float(new_tick.get("volume", 0.0))

		self._prices.append(price)
		self._volumes.append(volume)

		min_required = max(
			self.ma_window + 1,
			self.long_ma_window + 1,
			self.vol_window + 1,
			self.momentum_window + 1,
		)
		if len(self._prices) < min_required:
			return None

		prices = pd.Series(self._prices, dtype="float64")
		volumes = pd.Series(self._volumes, dtype="float64")
		rolling_avg_20 = float(prices.iloc[-self.ma_window :].mean())
		rolling_avg_50 = float(prices.iloc[-self.long_ma_window :].mean())

		vol_slice = prices.iloc[-self.vol_window :]
		volatility = float(vol_slice.max() - vol_slice.min())
		log_returns = np.log(vol_slice / vol_slice.shift(1)).dropna()
		realized_vol_short = float(log_returns.std(ddof=0)) if len(log_returns) > 0 else 0.0

		long_slice = prices.iloc[-(self.long_ma_window + 1) :]
		log_returns_long = np.log(long_slice / long_slice.shift(1)).dropna()
		realized_vol_long = float(log_returns_long.std(ddof=0)) if len(log_returns_long) > 0 else 0.0

		current_price = float(prices.iloc[-1])
		past_price = float(prices.iloc[-(self.momentum_window + 1)])
		momentum = float((current_price / past_price) - 1.0) if past_price > 0 else 0.0
		spread_bps = float(((vol_slice.max() - vol_slice.min()) / max(current_price, 1e-12)) * 1e4)

		price_diff = vol_slice.diff().fillna(0.0)
		vol_slice_volume = volumes.iloc[-self.vol_window :]
		signed_volume = np.sign(price_diff.to_numpy()) * vol_slice_volume.to_numpy()
		total_volume = float(vol_slice_volume.sum())
		book_imbalance = float(signed_volume.sum() / total_volume) if total_volume > 0 else 0.0

		volume_short = volumes.iloc[-self.ma_window :]
		volume_long = volumes.iloc[-self.long_ma_window :]
		volume_mean_short = float(volume_short.mean())
		volume_std_short = float(volume_short.std(ddof=0))
		rel_volume = float(volume_short.iloc[-1] / volume_long.mean()) if float(volume_long.mean()) > 0 else 0.0
		volume_zscore = (
			float((volume_short.iloc[-1] - volume_mean_short) / volume_std_short)
			if volume_std_short > 0
			else 0.0
		)

		short_ma_series = prices.rolling(window=self.ma_window).mean().dropna()
		long_ma_series = prices.rolling(window=self.long_ma_window).mean().dropna()
		trend_slope_short = self._slope(short_ma_series.iloc[-self.ma_window :])
		trend_slope_long = self._slope(long_ma_series.iloc[-self.ma_window :])
		distance_to_ma50 = (
			float((current_price - rolling_avg_50) / rolling_avg_50) if rolling_avg_50 > 0 else 0.0
		)

		self._latest_features = {
			"rolling_avg_20": float(np.round(rolling_avg_20, 8)),
			"rolling_avg_50": float(np.round(rolling_avg_50, 8)),
			"volatility": float(np.round(volatility, 8)),
			"momentum": float(np.round(momentum, 8)),
			"realized_vol_short": float(np.round(realized_vol_short, 8)),
			"realized_vol_long": float(np.round(realized_vol_long, 8)),
			"spread_bps": float(np.round(spread_bps, 8)),
			"book_imbalance": float(np.round(book_imbalance, 8)),
			"rel_volume": float(np.round(rel_volume, 8)),
			"volume_zscore": float(np.round(volume_zscore, 8)),
			"trend_slope_short": float(np.round(trend_slope_short, 8)),
			"trend_slope_long": float(np.round(trend_slope_long, 8)),
			"distance_to_ma50": float(np.round(distance_to_ma50, 8)),
		}

		if self.debug:
			print(
				"[feature_engine]"
				f" avg20={self._latest_features['rolling_avg_20']:.4f}"
				f" avg50={self._latest_features['rolling_avg_50']:.4f}"
				f" vol={self._latest_features['volatility']:.6f}"
				f" mom={self._latest_features['momentum']:.6f}"
				f" rv_s={self._latest_features['realized_vol_short']:.6f}"
				f" rv_l={self._latest_features['realized_vol_long']:.6f}"
			)

		return self._latest_features

	def get_latest_features(self) -> Optional[Dict[str, float]]:
		"""Return latest computed feature vector."""
		return self._latest_features

	def update(self, tick: Tick) -> Optional[FeatureSnapshot]:
		"""Consume a tick and return features when enough history exists.

		Returns None until the engine has enough prices for all windows.
		"""
		feature_vector = self.update_features(tick)
		if feature_vector is None:
			return None

		snapshot = FeatureSnapshot(
			symbol=tick.symbol,
			timestamp=tick.timestamp,
			price=float(tick.price),
			rolling_mean=feature_vector["rolling_avg_20"],
			rolling_volatility=feature_vector["volatility"],
			momentum=feature_vector["momentum"],
			realized_vol_short=feature_vector["realized_vol_short"],
			realized_vol_long=feature_vector["realized_vol_long"],
			spread_bps=feature_vector["spread_bps"],
			book_imbalance=feature_vector["book_imbalance"],
			rel_volume=feature_vector["rel_volume"],
			volume_zscore=feature_vector["volume_zscore"],
			trend_slope_short=feature_vector["trend_slope_short"],
			trend_slope_long=feature_vector["trend_slope_long"],
			distance_to_ma50=feature_vector["distance_to_ma50"],
		)

		return snapshot

	@staticmethod
	def _slope(values: pd.Series) -> float:
		if len(values) < 2:
			return 0.0
		y = values.to_numpy(dtype="float64")
		x = np.arange(len(y), dtype="float64")
		return float(np.polyfit(x, y, 1)[0])
