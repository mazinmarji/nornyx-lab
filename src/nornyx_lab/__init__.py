"""nornyx-lab — practical AI governance you can run.

A companion lab for *Governed Agentic Systems* (First Edition). Every lab runs
the real, published Nornyx toolchain; nothing here simulates it.
"""

from __future__ import annotations

__version__ = "1.0.0"

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
