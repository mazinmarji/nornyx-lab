"""Recompute the payload digest here rather than believing the one that arrived.

``sync.payload_digest`` is a field in an unauthenticated request from the open
internet. Reading it and using it as the idempotency key means a client — or
anything that rewrote the request in transit — decides which stored record a
payload is considered identical to. Two consequences follow directly: a stale
digest attached to changed content makes the gateway treat a *different*
session state as unchanged and skip the update, and a colliding digest makes
two genuinely different payloads share an identity.

So the digest is derived, not accepted. After validation the parsed payload is
canonicalised exactly as the Academy canonicalises it, hashed, and compared. A
mismatch is refused before anything touches GitHub or the synchronisation store,
and every downstream decision uses the recomputed value.

The canonical form is deliberately the same three rules on both sides —
``sync`` excluded, keys sorted, no insignificant whitespace — because a digest
that only one implementation can reproduce verifies nothing.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import FeedbackPayload


class DigestMismatch(ValueError):
    """The payload does not hash to the digest that was submitted with it."""

    def __init__(self, expected: str, submitted: str) -> None:
        # The values are both non-secret hashes of data the sender already has,
        # but there is no reason to echo them, so the message stays generic.
        super().__init__("payload digest does not match the payload")
        self.expected = expected
        self.submitted = submitted


def canonical_body(payload: FeedbackPayload) -> str:
    """The exact bytes both sides hash, as a string.

    ``sync`` is excluded because it carries the digest itself and the generation
    timestamp: including either would make the digest depend on itself, and make
    an otherwise unchanged session look changed on every regeneration.
    """

    document: dict[str, Any] = payload.model_dump(mode="json", exclude_none=False)
    document.pop("sync", None)
    return json.dumps(document, sort_keys=True, separators=(",", ":"))


def compute_digest(payload: FeedbackPayload) -> str:
    return f"sha256:{hashlib.sha256(canonical_body(payload).encode('utf-8')).hexdigest()}"


def verified_digest(payload: FeedbackPayload) -> str:
    """Return the digest this payload actually has, or refuse.

    The returned value — never ``payload.sync.payload_digest`` — is what the
    rest of the service uses as the session's content identity.
    """

    recomputed = compute_digest(payload)
    submitted = payload.sync.payload_digest
    # Constant-time comparison is not required: both values are hashes of data
    # the caller supplied and neither is a secret. Plain equality is used so the
    # comparison being performed is obvious.
    if recomputed != submitted:
        raise DigestMismatch(expected=recomputed, submitted=submitted)
    return recomputed


__all__ = ["DigestMismatch", "canonical_body", "compute_digest", "verified_digest"]
