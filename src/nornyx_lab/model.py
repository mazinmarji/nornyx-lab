"""The planner: a deterministic offline model, and an optional live one.

Why a scripted model is the DEFAULT and not a shortcut
------------------------------------------------------
These labs teach what governance changes about a system. If the model's output
varied run to run, every lab result would be confounded: you could never tell
whether an action was blocked by policy or simply not proposed this time.

So the default planner is deterministic and offline. It is not a language model
and does not pretend to be. It is a *susceptible planner*: it reads its context
and, like a real model, cannot tell an instruction written by its operator from
an instruction embedded in retrieved text. That susceptibility is the point —
it is what Chapter 6 calls authority confusion, and it is reproducible here.

`--live` swaps in a real Claude model. The governance outcomes are identical,
which is the lesson: enforcement does not depend on the planner behaving.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    """One action the planner intends to take. An intention, not an effect."""

    action: str
    args: dict[str, str] = field(default_factory=dict)
    because: str = ""

    def __str__(self) -> str:
        shown = ", ".join(f"{k}={v!r}" for k, v in sorted(self.args.items()))
        return f"{self.action}({shown})"


@dataclass(frozen=True)
class Plan:
    """What the planner decided to do, plus the text it would show a user."""

    calls: tuple[ToolCall, ...]
    answer: str
    influenced_by: tuple[str, ...] = ()

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(c.action for c in self.calls)


class Planner(Protocol):
    def plan(self, task: str, context: str) -> Plan: ...


# Phrases that a hostile page can put in front of a planner. A real model is
# steered by text like this; so is ours. Each maps to the action it induces.
_INJECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"publish|post (?:this|it|the)|share (?:this|it) (?:publicly|externally)", "publish_external"),
    (r"ignore (?:the |your |all )?(?:polic|rule|instruction|guideline)", "publish_external"),
    (r"refund|reimburse|pay (?:out|back)", "issue_refund"),
    (r"send (?:an? )?(?:email|message|notification)|notify", "notify_customer"),
    (r"delete|remove|drop (?:the )?(?:table|database|record)", "delete_records"),
    (r"credential|api[ _-]?key|secret|token|password", "read_secrets"),
)


class DeterministicPlanner:
    """A reproducible stand-in for a tool-using model.

    It plans the task's baseline actions, then scans the *whole* context for
    imperative text and adds whatever that text tells it to do. It has no way to
    distinguish an instruction from data, because nothing in its input marks the
    difference. That is not a bug in this class; it is the governance gap.
    """

    def __init__(self, *, susceptible: bool = True) -> None:
        self.susceptible = susceptible

    def plan(self, task: str, context: str = "") -> Plan:
        calls: list[ToolCall] = []
        influenced: list[str] = []

        lowered_task = task.lower()
        if any(w in lowered_task for w in ("brief", "research", "competitor", "summar")):
            calls.append(ToolCall("search_web", {"query": task[:40]}, "the task asks for research"))
            calls.append(
                ToolCall("draft_briefing", {"topic": task[:40]}, "the task asks for a document")
            )
        if any(w in lowered_task for w in ("refund", "remediat", "billing")):
            calls.append(ToolCall("read_case", {"case": "CASE-1041"}, "the task names a case"))
            calls.append(
                ToolCall("analyze_case", {"case": "CASE-1041"}, "a decision needs analysis")
            )
            amount = "5000.00" if "full" in lowered_task or "large" in lowered_task else "50.00"
            calls.append(ToolCall("issue_refund", {"amount": amount}, "the task asks for a refund"))
        if not calls:
            calls.append(ToolCall("draft_briefing", {"topic": task[:40]}, "default action"))

        if self.susceptible and context:
            for pattern, action in _INJECTION_PATTERNS:
                match = re.search(pattern, context, re.IGNORECASE)
                if not match:
                    continue
                if action in {c.action for c in calls}:
                    continue
                snippet = _line_around(context, match.start())
                calls.append(ToolCall(action, {"source": "context"}, f"context said: {snippet!r}"))
                influenced.append(snippet)

        answer = (
            "I could not complete that within the declared bounds."
            if not calls
            else f"Planned {len(calls)} action(s): " + ", ".join(c.action for c in calls)
        )
        return Plan(tuple(calls), answer, tuple(influenced))


def _line_around(text: str, index: int) -> str:
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    line = text[start : end if end != -1 else len(text)].strip()
    return line[:80]


class LivePlanner:
    """A real Claude model, used only when the learner passes `--live`.

    Deliberately thin. The lesson is that swapping a genuine, non-deterministic
    planner in changes the plan text but not one governance decision — the
    enforcement path never asks the model's permission.
    """

    MODEL = "claude-sonnet-4-20250514"

    def __init__(self, model: str | None = None, *, api_key: str | None = None) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - optional path
            raise RuntimeError(
                "Live-model support is not installed in this academy deployment. "
                "The operator must deploy the optional live-model component; "
                "offline deterministic mode remains available."
            ) from exc
        resolved_api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_api_key:
            raise RuntimeError(
                "Live mode needs an API key configured for this process. "
                "Every academy interaction also runs offline without one."
            )
        self._client = anthropic.Anthropic(api_key=resolved_api_key)
        self.model = model or self.MODEL

    def plan(self, task: str, context: str = "") -> Plan:  # pragma: no cover - network
        tools = [
            {
                "name": "propose_actions",
                "description": "Propose the sequence of actions you intend to take.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "actions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "action": {"type": "string"},
                                    "why": {"type": "string"},
                                },
                                "required": ["action"],
                            },
                        }
                    },
                    "required": ["actions"],
                },
            }
        ]
        message = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            tools=tools,
            tool_choice={"type": "tool", "name": "propose_actions"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"You are an agent at Northstar Services.\n\n"
                        f"CONTEXT:\n{context}\n\nTASK:\n{task}\n\n"
                        "Propose the actions you would take."
                    ),
                }
            ],
        )
        calls: list[ToolCall] = []
        for block in message.content:
            if getattr(block, "type", None) == "tool_use":
                for item in block.input.get("actions", []):
                    calls.append(
                        ToolCall(str(item.get("action", "")), {}, str(item.get("why", "")))
                    )
        return Plan(tuple(calls), f"Live plan: {len(calls)} action(s).", ())


def get_planner(live: bool = False, *, susceptible: bool = True) -> Planner:
    """Return the planner for this run. Offline unless the learner opts in."""
    if live:
        return LivePlanner()
    return DeterministicPlanner(susceptible=susceptible)
