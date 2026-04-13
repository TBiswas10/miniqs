"""Strategy evaluator compatibility wrapper.

This module re-exports from the package for backward compatibility.
New code should import from signals.evaluator instead.
"""

from src.miniqs.signals.evaluator import emit_signal_event, evaluate_signals, evaluate_signals_v2

__all__ = ["emit_signal_event", "evaluate_signals", "evaluate_signals_v2"]
