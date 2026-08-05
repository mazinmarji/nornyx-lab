"""Suite-wide guards.

Several labs demonstrate a control by *breaking* something real — tampering
with a generated artifact (Lab 11), corrupting a lock (Lab 15), weakening an
approval declaration (Lab 07, 23) — and restoring it in a `finally`. That is
deliberate: a lab that only ever showed the happy path would not teach the
gate.

The cost is that those tests mutate shared state under `contracts/`, so the
suite must run **serially**. Two concurrent runs will see each other's
half-broken tree and produce a baffling `AN_LOCK_REVISION_MISMATCH`.

Rather than let someone lose an afternoon to that, we detect it and say so.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Refuse to run under xdist, with an explanation rather than a crash."""
    if config.pluginmanager.hasplugin("xdist"):
        numprocesses = getattr(config.option, "numprocesses", None)
        if numprocesses:
            raise pytest.UsageError(
                "nornyx-lab's suite must run serially.\n\n"
                "Labs 07, 11, 15, and 23 deliberately break a real contract, lock, or "
                "generated artifact and restore it in a `finally`. Running them in "
                "parallel lets one worker observe another's half-broken tree, which "
                "surfaces as a confusing AN_LOCK_* or drift failure that has nothing "
                "to do with your change.\n\n"
                "Run `pytest labs tests -q -rs` (or `make test`) without -n."
            )


def pytest_report_header(config: pytest.Config) -> list[str]:
    from nornyx_lab.constants import LAB_AS_OF, PINNED_ADAPTERS, PINNED_NORNYX

    return [
        f"nornyx-lab: nornyx=={PINNED_NORNYX}, adapters=={PINNED_ADAPTERS}, as-of={LAB_AS_OF}",
    ]
