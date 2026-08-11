"""The documentation and the learner-facing copy are repository claims too.

This repository's recurring failure mode is prose that says more than the code
does. These tests hold the feedback feature's wording to what is actually
implemented — particularly the two claims that would be most damaging if wrong:
that the feedback is anonymous, and that the gateway is deployed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
FEEDBACK_DOC = REPOSITORY / "docs" / "LEARNER_FEEDBACK.md"
GATEWAY_README = REPOSITORY / "gateway" / "README.md"
README = REPOSITORY / "README.md"
SECURITY = REPOSITORY / "docs" / "SECURITY.md"

#: Learner-visible copy and the docs that describe the feature. A claim in any of
#: these is a claim the repository is making.
FEEDBACK_SURFACES = (
    FEEDBACK_DOC,
    GATEWAY_README,
    REPOSITORY / "frontend" / "src" / "components" / "LearnerFeedback.tsx",
    REPOSITORY / "frontend" / "src" / "pages" / "FeedbackPage.tsx",
    REPOSITORY / "src" / "nornyx_lab" / "academy" / "feedback.py",
)


def _flat(path: Path) -> str:
    """Document text with line wrapping removed.

    A claim does not stop being made because it happened to wrap. Comparing on
    normalised whitespace keeps these checks about content rather than about
    where the paragraph reflowed.
    """

    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def _prose_only(path: Path) -> str:
    """The document minus its claims-audit table.

    That table exists to enumerate claims *and their status*, including the ones
    the product explicitly does not make — "The gateway is deployed … **not
    implemented**". Scanning it for forbidden phrases would flag the very rows
    that keep the documentation honest, so the negative-claim checks read the
    prose and the audit gets its own dedicated assertions.
    """

    text = path.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", text.split("## Claims audit")[0])


def _feedback_paragraphs(path: Path) -> list[str]:
    """Paragraphs of a document that are about feedback.

    README and SECURITY.md cover the whole product, so only their feedback
    sections are in scope here — a sentence about container hardening elsewhere
    is not a feedback claim.
    """

    text = _prose_only(path)
    return [block for block in re.split(r"(?<=[.!?]) ", text) if "feedback" in block.lower()]


def test_the_feature_is_never_called_anonymous() -> None:
    """The one word this feature must not use about itself.

    A learner can type their name into a comment box, hosting infrastructure
    sees network metadata, and GitHub keeps its own logs. "Anonymous" would be
    false in three independent ways, so the product says "pseudonymous" and
    "no identifying information is intentionally collected".
    """

    for path in FEEDBACK_SURFACES:
        text = _flat(path).lower()
        for offence in re.finditer(r"anonymous|anonymised|anonymized", text):
            window = text[max(0, offence.start() - 120) : offence.end() + 120]
            # The doc is allowed to explain *why* the word is not used.
            assert "not" in window or "never" in window or "preclude" in window, (
                f"{path.name} calls learner feedback anonymous: …{window}…"
            )


def test_the_documentation_states_the_pseudonymous_framing() -> None:
    text = _flat(FEEDBACK_DOC)
    assert "No identifying information is intentionally collected by Nornyx Lab." in text
    assert "Pseudonymous learner feedback." in text


@pytest.mark.parametrize("path", [FEEDBACK_DOC, GATEWAY_README])
def test_the_gateway_is_not_described_as_deployed_or_operational(path) -> None:
    """Code existing is not a deployment, and the docs must not blur the two."""

    flat = _flat(path).lower()
    assert "deployment-ready" in flat
    assert "not yet operational" in flat or "not deployed" in flat

    for sentence in re.split(r"(?<=[.!?]) ", _prose_only(path)):
        lowered = sentence.lower()
        if "gateway" not in lowered:
            continue
        for claim in ("is deployed", "is live", "is running in production", "is operational"):
            assert claim not in lowered, f"{path.name} claims the gateway {claim}: {sentence}"


def test_no_production_feedback_url_is_published_anywhere() -> None:
    for path in (*FEEDBACK_SURFACES, README, SECURITY):
        text = _flat(path)
        for invented in ("feedback.nornyx.", "gateway.nornyx.", "https://nornyx-feedback"):
            assert invented not in text, f"{path.name} publishes an endpoint that does not exist"


def test_the_docs_do_not_promise_remote_deletion() -> None:
    for path in (FEEDBACK_DOC, README, SECURITY):
        for block in _feedback_paragraphs(path):
            lowered = block.lower()
            for claim in (
                "deletes it from github",
                "removes it from github",
                "erases your feedback everywhere",
                "recall your feedback",
            ):
                assert claim not in lowered, f"{path.name} promises remote deletion"


def test_the_docs_state_the_competence_isolation_as_the_headline() -> None:
    text = _flat(FEEDBACK_DOC)
    assert "not evidence of competence" in text.lower()
    for field in (
        "assessment scoring",
        "module completion",
        "concepts mastered",
        "capstone eligibility",
        "AdvancedStanding",
    ):
        assert field in text, f"the isolation claim omits {field}"


def test_the_docs_list_both_what_is_collected_and_what_is_excluded() -> None:
    text = _flat(FEEDBACK_DOC)
    for excluded in (
        "email address",
        "hostname",
        "OS username",
        "filesystem paths",
        "API keys",
        "environment variables",
        "hardware fingerprint",
        "browser fingerprint",
        "IP address",
        "raw assessment answers",
    ):
        assert excluded in text, f"the exclusion list omits {excluded!r}"


def test_the_claims_audit_exists_and_marks_the_unimplemented_claims() -> None:
    """A claims table that only lists successes is not an audit."""

    text = _flat(FEEDBACK_DOC)
    assert "## Claims audit" in text
    assert "**not implemented**" in text
    assert "**not claimed**" in text
    assert "configuration-dependent" in text
    assert "## Residual limitations" in text


def test_the_learner_facing_copy_never_says_sent_before_it_is(tmp_path) -> None:
    """The UI must not carry a hard-coded success sentence of its own."""

    component = (REPOSITORY / "frontend" / "src" / "components" / "LearnerFeedback.tsx").read_text(
        encoding="utf-8"
    )
    # The only place this sentence may exist is the backend's message table.
    assert "sent to the maintainers." not in component.replace(
        "Nothing has been sent.", ""
    ).replace("recall anything already received.", ""), (
        "the browser hard-codes a delivery-success sentence instead of rendering "
        "the state the backend reported"
    )


def test_the_learner_facing_state_wording_is_exactly_what_was_specified() -> None:
    """These four sentences are the product contract, not a style choice.

    Each states one thing precisely: that the record is local, that nothing has
    left, that later feedback will leave, or that sending is unavailable — and
    the last two are phrased as facts about the installation rather than as
    something the learner did wrong. Pinned so a later edit is a deliberate
    decision.
    """

    from nornyx_lab.academy.feedback import LEARNER_MESSAGES

    assert LEARNER_MESSAGES["no_consent"] == (
        "Feedback saved on this computer. Nothing has been sent to the maintainers."
    )
    assert LEARNER_MESSAGES["consented"] == (
        "Feedback saved on this computer. Future feedback from this learning session will "
        "also be sent to the maintainers."
    )
    assert LEARNER_MESSAGES["unavailable"] == (
        "Your feedback is saved locally. Sending it to the maintainers is temporarily unavailable."
    )
    assert LEARNER_MESSAGES["not_configured"] == (
        "Feedback is saved locally. This installation is not configured to send feedback to "
        "the maintainers."
    )


def test_no_learner_facing_state_blames_the_learner() -> None:
    from nornyx_lab.academy.feedback import LEARNER_MESSAGES

    for key, message in LEARNER_MESSAGES.items():
        lowered = message.lower()
        for blame in ("you must", "you failed", "error", "invalid", "you did not"):
            assert blame not in lowered, f"the {key} state blames the learner: {message}"


def test_no_learner_facing_state_exposes_internal_detail() -> None:
    from nornyx_lab.academy.feedback import LEARNER_MESSAGES

    for message in LEARNER_MESSAGES.values():
        for leak in ("http", "://", "traceback", "sqlite", "token", "\\", "/app"):
            assert leak not in message.lower(), f"a learner state leaks internals: {message}"


def test_the_single_replica_scope_of_one_issue_per_session_is_stated() -> None:
    """The guarantee is per process, and saying otherwise would be an overclaim.

    Serialising synchronisation closes the race inside one gateway. It is not
    distributed coordination, so any document that promises one issue per
    session has to say where that promise stops.
    """

    for path in (FEEDBACK_DOC, GATEWAY_README):
        flat = _flat(path).lower()
        assert "single-replica" in flat or "single replica" in flat, (
            f"{path.name} promises one issue per session without naming the scope"
        )
        assert "replicas" in flat


@pytest.mark.parametrize("path", [FEEDBACK_DOC, GATEWAY_README, SECURITY])
def test_no_document_claims_exactly_once_creation_across_replicas(path) -> None:
    flat = _flat(path).lower()
    for overclaim in (
        "exactly-once across replicas",
        "exactly once across replicas",
        "distributed coordination guarantees",
        "guarantees one issue per session across",
    ):
        assert overclaim not in flat, f"{path.name} claims cross-replica exactly-once"


def test_the_inertness_claim_covers_the_whole_wire_surface_or_is_narrowed() -> None:
    """The old absolute sentence was true of comments and not of the rest.

    Timestamps and version strings reached the rendered summary bounded only by
    length. Now every caller-supplied string either has a Markdown-inert syntax
    or is fenced — and the wording has to say which claim is being made.
    """

    for path in (FEEDBACK_DOC, GATEWAY_README, SECURITY):
        flat = _flat(path)
        assert "no learner-authored character is ever emitted as Markdown" not in flat, (
            f"{path.name} still carries the unqualified inertness sentence"
        )

    canonical = _flat(FEEDBACK_DOC)
    assert "every caller-supplied string either has a syntax" in canonical
    assert "or is emitted only inside a fenced block" in canonical


def test_the_evidence_expiry_behaviour_of_feedback_context_is_documented() -> None:
    flat = _flat(FEEDBACK_DOC)
    assert "Assessment context obeys evidence expiry" in flat
    assert "assessment_evidence_revision" in flat
    # The null-is-not-false distinction is the one an analyst can most easily
    # get wrong, so it has to be stated rather than implied.
    assert "different claim from" in flat


def test_the_gateway_digest_verification_is_documented() -> None:
    flat = _flat(FEEDBACK_DOC)
    assert "does not trust the digest it receives" in flat
    assert "digest_mismatch" in flat


def test_the_write_key_versus_public_marker_split_is_documented() -> None:
    """The published record must not carry the value that authorises writing to it."""

    canonical = _flat(FEEDBACK_DOC)
    assert "The write key is never published" in canonical
    assert "session_marker" in canonical
    assert "sha256" in canonical.lower()

    gateway = _flat(GATEWAY_README)
    assert "never written to GitHub" in gateway or "never published" in gateway


def test_the_embedded_issue_json_is_not_claimed_to_be_verbatim() -> None:
    """One field is deliberately substituted, so "exact payload" would be false."""

    canonical = _flat(FEEDBACK_DOC)
    assert "not** a verbatim copy" in canonical or "not a verbatim copy" in canonical

    for path in (FEEDBACK_DOC, GATEWAY_README, SECURITY):
        flat = _flat(path)
        for overclaim in (
            "the exact payload received",
            "exactly as received, minus nothing",
        ):
            assert overclaim not in flat, f"{path.name} claims the issue JSON is verbatim"


#: Prose the UUID -> marker redesign made false. Each of these described the
#: architecture accurately before that change, which is exactly why they
#: survived it — they read as correct to anyone not checking against the code.
PRE_MARKER_FORMULATIONS = (
    "full session UUID",
    "raw session UUID",
    "session UUID alone",
    "truncated session id",
    "truncated session identifier",
    "derived from the session UUID",
    "the exact payload as JSON",
)

#: Everywhere the redesign has to be described consistently.
MARKER_SURFACES = (
    FEEDBACK_DOC,
    GATEWAY_README,
    SECURITY,
    REPOSITORY / "gateway" / "src" / "nornyx_feedback_gateway" / "render.py",
    REPOSITORY / "gateway" / "src" / "nornyx_feedback_gateway" / "app.py",
    REPOSITORY / "gateway" / "src" / "nornyx_feedback_gateway" / "sync.py",
    REPOSITORY / "gateway" / "src" / "nornyx_feedback_gateway" / "identity.py",
)


@pytest.mark.parametrize("path", MARKER_SURFACES, ids=lambda p: p.name)
@pytest.mark.parametrize("stale", PRE_MARKER_FORMULATIONS)
def test_pre_marker_prose_cannot_return(path, stale) -> None:
    """Documentation drifts back. This is the ratchet."""

    flat = _flat(path)
    assert stale not in flat, (
        f"{path.name} describes the pre-marker architecture: {stale!r}. GitHub sees "
        "only sha256(uuid); the raw identifier is a private write key."
    )


def test_the_recovery_description_names_the_marker_not_the_uuid() -> None:
    """Recovery is where the stale wording hid longest, so pin the correction."""

    flat = _flat(FEEDBACK_DOC)
    assert "confirms identity against the full marker" in flat
    assert "raw UUID is never written to GitHub" in flat


def test_the_title_is_documented_as_deriving_from_the_marker() -> None:
    canonical = _flat(FEEDBACK_DOC)
    assert "title is derived from a prefix of the public correlation marker" in canonical
    render = _flat(REPOSITORY / "gateway" / "src" / "nornyx_feedback_gateway" / "render.py")
    assert "prefix of the public correlation marker" in render


def test_the_structural_properties_behind_the_prose_still_hold() -> None:
    """The prose is only worth policing if the behaviour it describes is real.

    Asserted structurally rather than by reading more text: the title really is
    built from the marker, the rendered document really does re-key the session,
    and the derivation really is one-way.
    """

    sys.path.insert(0, str(REPOSITORY / "gateway" / "src"))
    try:
        from nornyx_feedback_gateway.identity import derive_marker, title_fragment
        from nornyx_feedback_gateway.render import issue_title, session_marker
    finally:
        sys.path.remove(str(REPOSITORY / "gateway" / "src"))

    session = "7f21ac1e-4b3d-4c2a-9f10-2b5d6e7a8c90"
    marker = derive_marker(session)

    assert session not in issue_title(marker)
    assert title_fragment(marker) in issue_title(marker)
    assert session not in session_marker(marker)
    assert marker in session_marker(marker)
    assert marker != session


def test_the_timestamp_syntax_requirement_is_documented() -> None:
    """Parsing alone was the defect; the docs have to say why it was not enough."""

    canonical = _flat(FEEDBACK_DOC)
    assert "fromisoformat" in canonical
    assert "separator" in canonical
    security = _flat(SECURITY)
    assert "fromisoformat" in security


def test_one_canonical_document_owns_the_architecture_prose() -> None:
    """The same architecture explained in four files drifts in three of them."""

    detailed = (
        "Hosted Nornyx Feedback Gateway",
        "payload_digest",
        "feedback_sync_state",
    )
    for path in (README, SECURITY):
        text = _flat(path)
        for marker in detailed:
            assert marker not in text, (
                f"{path.name} duplicates detailed feedback architecture; it should "
                "link to docs/LEARNER_FEEDBACK.md instead"
            )
        assert "docs/LEARNER_FEEDBACK.md" in text or "LEARNER_FEEDBACK.md" in text
