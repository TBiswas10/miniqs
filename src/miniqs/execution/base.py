"""Base interfaces for trade execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class AbstractExecutor(ABC):
    """Formal interface for all execution engines."""

    @abstractmethod
    def execute(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a trade and return a standardized execution report."""
        pass
