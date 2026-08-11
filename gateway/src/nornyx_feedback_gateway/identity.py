"""Separate the private write key from the public correlation marker.

The intake is unauthenticated by design — no learner accounts — so whoever
presents a session's UUID can overwrite that session's issue. That was an
acceptable residual risk only while the UUID stayed private. It did not: the
rendered issue published it three times, in the summary line, in the HTML
recovery marker, and in the embedded JSON. With a public intake repository the
issue therefore published the exact locator needed to overwrite itself.

The fix keeps the trust model and removes the publication:

    session UUID          private write key, Academy -> gateway only
    sha256(session UUID)  public correlation marker, safe to publish

Only the marker reaches GitHub. Recovery still works because derivation is
deterministic: an incoming UUID produces the same marker every time, so a
gateway that has lost its database can still find the issue that already
represents the session.

Two deliberate choices:

* **Plain SHA-256, not an HMAC with a gateway-held key.** Recovery must survive
  a redeploy onto fresh storage, so derivation cannot depend on gateway-local
  state. A secret that must be backed up to keep recovery working is a secret
  that will be lost.
* **No salt.** For the same reason. A UUID4 has 122 bits of entropy, so the
  preimage space is not searchable; salting would buy nothing and would break
  determinism.

The marker is one-way. Publishing it does not let a reader compute the UUID, so
it cannot be replayed as the write key.
"""

from __future__ import annotations

import hashlib

#: How much of the marker appears in the issue title. Long enough that a
#: collision is not a practical concern, short enough to stay readable; identity
#: is confirmed against the full marker in the body regardless.
TITLE_PREFIX_LENGTH = 12


def derive_marker(session_id: str) -> str:
    """The public correlation marker for a private session identifier."""

    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def title_fragment(marker: str) -> str:
    return marker[:TITLE_PREFIX_LENGTH]


__all__ = ["TITLE_PREFIX_LENGTH", "derive_marker", "title_fragment"]
