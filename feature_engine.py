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
		history_len = max(ma_window, long_ma_window, vol_window, momentum_window + 1)
		self._prices: Deque[float] = deque(maxlen=history_len)
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
		else:
			price = float(new_tick["mid_price"])

		self._prices.append(price)

		min_required = max(self.ma_window, self.long_ma_window, self.vol_window, self.momentum_window + 1)
		if len(self._prices) < min_required:
			return None

		prices = pd.Series(self._prices, dtype="float64")
		rolling_avg_20 = float(prices.iloc[-self.ma_window :].mean())
		rolling_avg_50 = float(prices.iloc[-self.long_ma_window :].mean())

		vol_slice = prices.iloc[-self.vol_window :]
		volatility = float(vol_slice.max() - vol_slice.min())

		current_price = float(prices.iloc[-1])
		past_price = float(prices.iloc[-(self.momentum_window + 1)])
		momentum = float((current_price / past_price) - 1.0) if past_price > 0 else 0.0

		self._latest_features = {
			"rolling_avg_20": float(np.round(rolling_avg_20, 8)),
			"rolling_avg_50": float(np.round(rolling_avg_50, 8)),
			"volatility": float(np.round(volatility, 8)),
			"momentum": float(np.round(momentum, 8)),
		}

		if self.debug:
			print(
				"[feature_engine]"
				f" avg20={self._latest_features['rolling_avg_20']:.4f}"
				f" avg50={self._latest_features['rolling_avg_50']:.4f}"
				f" vol={self._latest_features['volatility']:.6f}"
				f" mom={self._latest_features['momentum']:.6f}"
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
		)

		return snapshot
