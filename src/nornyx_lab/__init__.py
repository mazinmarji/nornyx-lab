"""Nornyx Academy — browser-first practical AI and agent governance.

The package retains the verified lab domain while exposing structured academy
services. Business actions are deliberately inert simulations; Nornyx parsing,
decisions, locks, generation, and evidence validation use the released runtime.
"""

from __future__ import annotations

__version__ = "2.0.0"

from .constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from .ledger import Entry, Ledger
from .model import Plan, ToolCall, get_planner

__all__ = [
    "LAB_AS_OF",
    "LAB_SUBJECT_REVISION",
    "Ledger",
    "Entry",
    "Plan",
    "ToolCall",
    "get_planner",
]
