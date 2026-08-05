"""The side-effect ledger — the lab's instrument for proving prevention.

The central methodological claim of this repository is that you cannot learn
governance by reading refusal messages. A system that *says* "denied" and a
system that actually did not act are indistinguishable from the text alone.

So every business function in every lab writes to a ledger before and after it
does its work, and the labs assert on counts:

    attempts == 0 and completions == 0   ->  the work genuinely did not happen
    attempts == 1 and completions == 0   ->  it started and failed (not prevention)
    attempts == 1 and completions == 1   ->  it ran

That distinction is Chapter 14's negative-control discipline, and it is the
difference between a demo and a test.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Entry:
    """One observed side effect, stamped on a monotonic per-ledger counter."""

    seq: int
    event: str
    fields: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        extra = " ".join(f"{k}={v!r}" for k, v in sorted(self.fields.items()))
        return f"[{self.seq:02d}] {self.event}{(' ' + extra) if extra else ''}"


class Ledger:
    """An append-only record of what a run actually caused to happen.

    The clock is a counter, not the wall clock: two runs of the same lab produce
    identical ledgers, which is what lets `nornyx-lab check` assert on them.
    """

    def __init__(self, name: str = "run") -> None:
        self.name = name
        self._entries: list[Entry] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------- recording
    def record(self, event: str, **fields: Any) -> Entry:
        with self._lock:
            entry = Entry(len(self._entries) + 1, event, dict(fields))
            self._entries.append(entry)
            return entry

    def attempt(self, action: str, **fields: Any) -> Entry:
        """Record that a business callable was entered."""
        return self.record(f"{action}_attempted", **fields)

    def complete(self, action: str, **fields: Any) -> Entry:
        """Record that a business callable finished its effect."""
        return self.record(f"{action}_completed", **fields)

    def decision(self, code: str, effect: str, **fields: Any) -> Entry:
        """Record a governance decision on the SAME clock as the side effects.

        Stamping decisions and effects on one monotonic counter is what makes
        "was the decision recorded before the work ran?" a checkable question
        rather than a matter of trust.
        """
        return self.record("governance_decision", code=code, effect=effect, **fields)

    # -------------------------------------------------------------- querying
    @property
    def entries(self) -> list[Entry]:
        return list(self._entries)

    def count(self, event: str) -> int:
        return sum(1 for e in self._entries if e.event == event)

    def attempts(self, action: str) -> int:
        return self.count(f"{action}_attempted")

    def completions(self, action: str) -> int:
        return self.count(f"{action}_completed")

    def events(self) -> list[str]:
        return [e.event for e in self._entries]

    def codes(self) -> list[str]:
        return [
            str(e.fields.get("code")) for e in self._entries if e.event == "governance_decision"
        ]

    def decided_before_acting(self, action: str) -> bool:
        """True when the k-th entry into `action` is preceded by a k-th decision.

        A naive "a decision exists before the first execution" test passes even
        when one authorization is reused for many actions. This does not.
        """
        decisions = 0
        acted = 0
        for entry in self._entries:
            if entry.event == "governance_decision":
                decisions += 1
            elif entry.event == f"{action}_attempted":
                acted += 1
                if acted > decisions:
                    return False
        return True

    def touched(self) -> set[str]:
        """Business actions this ledger saw an attempt for."""
        return {
            e.event.removesuffix("_attempted")
            for e in self._entries
            if e.event.endswith("_attempted")
        }

    # --------------------------------------------------------------- export
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entries": [{"seq": e.seq, "event": e.event, **e.fields} for e in self._entries],
        }

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return p

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"<Ledger {self.name!r} entries={len(self._entries)}>"
