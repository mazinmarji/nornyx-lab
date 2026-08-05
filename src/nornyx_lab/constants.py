"""Values that every lab shares, and the reasons they are pinned.

Read this file early. Two of these constants exist because of a real property of
the governance model, not because of laziness, and the labs teach both.
"""

from __future__ import annotations

# ---------------------------------------------------------------- pinned time
#
# WHY THIS EXISTS (Chapters 9 and 12).
#
# The `agentic_network` profile expires approvals after P7D — seven days. That is
# a deliberate control: an approval that never expires is an approval nobody has
# to re-earn. It also means a contract committed to git STOPS VALIDATING a week
# after it was written, unless every command names the instant it is being
# validated at.
#
# So the labs pin one evaluation instant and pass it everywhere: to `nornyx
# check --as-of`, and to `load_authorizer(validation_as_of=...)`. Wall-clock time
# is one of the three classic destroyers of evaluation determinism (Ch. 7), and
# refusing to read the clock is how the labs stay reproducible in 2030.
#
# Lab 09 makes you move this value and watch approvals go stale.
LAB_AS_OF = "2026-06-01T12:00:00Z"

# The approval validity window that LAB_AS_OF sits inside. Exactly 7 days, the
# maximum the profile permits.
APPROVAL_ISSUED_AT = "2026-06-01T00:00:00Z"
APPROVAL_EXPIRES_AT = "2026-06-08T00:00:00Z"

# ------------------------------------------------------------ subject revision
#
# WHY THIS EXISTS (Chapters 12 and 20).
#
# Every governed decision binds to the exact revision of the thing it governs. In
# a real deployment this is the git commit of the contract repository. The labs
# use one fixed synthetic revision so that generated artifacts, locks, and
# evidence are byte-identical on every machine — which is what makes the drift
# gate in Lab 17 a real gate rather than a coin flip.
LAB_SUBJECT_REVISION = "git:5eed1e55c0ffee1abadcafe0ddba11ed15ea5e11"

# --------------------------------------------------------------- profile facts
#
# The agentic_network profile fixes these. A contract cannot choose them, and
# choosing differently produces AN_APPROVAL_DECLARED_ROLE_UNAUTHORIZED and
# friends. Lab 14 walks into that wall on purpose.
NETWORK_APPROVAL_NAME = "agentic_network_authority"
NETWORK_APPROVER_ROLE = "network_governance_owner"

# Versions this repository was built and verified against.
PINNED_NORNYX = "1.11.0"
PINNED_ADAPTERS = "0.3.0"

# Where per-user progress lives (gitignored).
PROGRESS_DIR = ".nornyx-lab"
