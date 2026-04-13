"""Risk manager compatibility wrapper.

This module re-exports from the package for backward compatibility.
New code should import from risk.engine instead.
"""

from src.miniqs.risk.engine import RiskConfig, RiskEngine, check_risk

__all__ = ["RiskConfig", "RiskEngine", "check_risk"]
