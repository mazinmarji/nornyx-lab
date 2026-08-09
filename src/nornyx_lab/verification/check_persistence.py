"""Validate that a learner record survived a restart.

Reads `[before, after]` — two `/api/v1/progress` payloads as a JSON array — on
stdin and reports whether any module lost executions across the restart. The
composition mounts a named volume for exactly this, so losing a record means the
promise the compose file makes is not being kept.

Packaged for the same reason as `check_counters`: this was a multiline program
embedded in a shell argument. It happened to use double-quoted keys and so
survived, but the pattern is the one that broke step 9 the first time B5 ran
independently. A program the shell can rewrite is a program no test truly
covers.

Exit codes match `check_counters`:

    0   the record survived
    1   the product lost data, or reported something unusable
    4   this checker could not decide
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .check_counters import (
    EXIT_OK,
    EXIT_PRODUCT_FAILURE,
    EXIT_VERIFIER_FAILURE,
    ProductContractError,
)


def _executions(payload: Any, label: str) -> dict[str, int]:
    if not isinstance(payload, dict):
        raise ProductContractError(f"the {label} progress payload is not an object")
    modules = payload.get("modules")
    if not isinstance(modules, list):
        raise ProductContractError(f"the {label} progress payload has no 'modules' list")

    counts: dict[str, int] = {}
    for module in modules:
        if not isinstance(module, dict):
            raise ProductContractError(f"a {label} module entry is not an object")
        module_id = module.get("module_id")
        executions = module.get("executions", 0)
        if not isinstance(module_id, str) or not isinstance(executions, int):
            raise ProductContractError(
                f"a {label} module entry has an unusable id/executions pair: "
                f"{module_id!r}/{executions!r}"
            )
        counts[module_id] = executions
    return counts


def evaluate(before: Any, after: Any) -> list[str]:
    """Return the modules that lost executions. Empty means the record held."""
    b = _executions(before, "pre-restart")
    a = _executions(after, "post-restart")
    if not any(b.values()):
        raise ProductContractError(
            "no module had recorded an execution before the restart, so persistence "
            "cannot be demonstrated by this comparison"
        )
    return sorted(key for key, value in b.items() if a.get(key, 0) < value)


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"PRODUCT PROBLEM: the progress payloads are not valid JSON: {exc}")
        return EXIT_PRODUCT_FAILURE
    except Exception as exc:  # pragma: no cover - stdin is provided by the caller
        print(f"VERIFIER ERROR: could not read the payloads: {exc}")
        return EXIT_VERIFIER_FAILURE

    if not isinstance(payload, list) or len(payload) != 2:
        print("VERIFIER ERROR: expected a two-element [before, after] array on stdin")
        return EXIT_VERIFIER_FAILURE

    try:
        lost = evaluate(payload[0], payload[1])
    except ProductContractError as exc:
        print(f"PRODUCT PROBLEM: {exc}")
        return EXIT_PRODUCT_FAILURE
    except Exception as exc:  # noqa: BLE001 - see check_counters
        print(f"VERIFIER ERROR: {type(exc).__name__}: {exc}")
        return EXIT_VERIFIER_FAILURE

    print(f"modules with fewer executions after restart: {lost or 'none'}")
    if lost:
        print(f"PRODUCT PROBLEM: the learner record lost executions for {lost}")
        return EXIT_PRODUCT_FAILURE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
