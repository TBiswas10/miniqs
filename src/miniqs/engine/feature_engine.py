"""Feature engineering compatibility wrapper.

This module re-exports from the package for backward compatibility.
New code should import from engine.feature instead.
"""

from src.miniqs.engine.feature import FeatureEngine, FeatureSnapshot

__all__ = ["FeatureEngine", "FeatureSnapshot"]
