# Security and sandbox boundary

## Threat model

Nornyx Academy is a local training application. The initial deployment assumes one trusted
operator and one local learner record. It does not provide authentication, tenant separation,
internet-facing hardening, or safe execution of arbitrary learner code.

The primary risks in scope are:

- a training scenario causing a real business or network side effect;
- legacy exercises modifying committed source or another run;
- prompt-injected text being treated as application authority;
- live-model secrets being persisted, logged, or returned;
- optional frameworks silently changing the meaning of a lesson;
- workbench input becoming arbitrary file or code execution;
- browser content injection or cross-origin data leakage;
- overclaiming what supplied evidence or cooperative enforcement proves.

## Default side-effect boundary

All business actions are inert in-process functions backed by the academy ledger. Names such as
`publish_external`, `issue_refund`, `notify_customer`, or `delete_records` describe the lesson;
they do not perform those external operations. The default product does not send email, transfer
money, publish content, push repositories, install packages, activate MCP servers, upload user
data, or call a model provider.

The ledger records entry into and successful return from the inert callable:

- `0 attempts / 0 completions`: the protected callable was not entered;
- `1 / 0`: it was entered but did not complete;
- `1 / 1`: the inert training effect completed;
- absent or incomplete observation: no definite counter claim.

These counters do not attest to an external world.

## Execution isolation

Original lab code runs in a new OS temporary directory. The runner copies the fixture directories
needed by a lab, applies a context-local repository-root override, executes serially within that
copy, sanitizes results, and removes the copy in `finally`. It never lets a learner submit source,
shell arguments, package names, paths, or Python.

The guided contract workbench accepts a closed set of semantic operations and targets. It deep
copies a known contract, renders to an isolated temporary file, and calls real Nornyx parse/check/
generation APIs. It cannot save to the committed source. A valid mutation can still make the old
lock stale; the UI reports semantic validity and lock status separately.

CrewAI tracing/telemetry environment controls are set before import to prevent its first-run
initialization from spawning a process during guarded adapter execution.

## Live-model secrets

Live mode is disabled by default. When explicitly enabled:

- the API accepts the key only over the local same-origin connection;
- Pydantic represents it as a secret;
- the store keeps it only in process memory;
- responses contain only `configured: true|false`;
- it is excluded from progress, exports, evidence, logs, and scenario results;
- disabling live mode or restarting clears it;
- a missing SDK/key/network response returns an explicit error;
- no deterministic result is substituted.

Do not expose the local service to an untrusted network while using an in-memory key. For shared
or remote deployment, add TLS, authentication, secret-manager integration, CSRF protection,
rate limits, tenant-isolated storage, and an outbound policy before enabling live mode.

## Learner feedback and the GitHub credential boundary

Optional learner feedback adds the academy's only outbound data path. It is
designed so the learner installation holds no external authority:

- the browser sends learner perception only; scores, statuses, versions, the
  competence revision, and the session identifier are derived server-side, and a
  request carrying any of them is rejected rather than silently stripped;
- nothing is transmitted before an explicit, never-pre-checked opt-in, and the
  consent state is read from the database rather than from the request;
- the local write commits before any network call and is never rolled back by a
  delivery failure;
- the outbound endpoint must be HTTPS outside loopback, carries an explicit
  timeout, and refuses redirects;
- **no GitHub credential exists in the learner distribution.** The hosted
  feedback gateway is a separate project under `gateway/`, is not copied into
  the production image, is excluded by `.dockerignore`, and is the only holder
  of GitHub write authority;
- the gateway injects its token at runtime, never as a build argument, and never
  returns, logs, or persists it. An unconfigured gateway fails closed;
- every caller-supplied string in the payload either has a syntax that carries no
  meaning in Markdown — timestamps pinned to an explicit ASCII form *and then*
  parsed, constrained versions, revisions and identifiers — or is emitted only
  inside a code fence sized so it cannot close its own fence. Pinning the
  timestamp form matters because `datetime.fromisoformat` accepts any single
  character as the date/time separator, so a parseable instant could otherwise
  carry a backtick or a newline into the rendered summary. Learner free text is
  stored and transmitted exactly as typed and made inert at rendering rather
  than edited. Issue title, labels, repository, and state come from
  configuration alone;
- the session identifier that authorises overwriting a feedback issue is never
  published. GitHub receives a one-way `sha256` marker derived from it, in the
  title, the recovery comment, the summary and the embedded JSON, and the
  gateway's own store is keyed on the marker as well;
- the gateway recomputes the payload digest from what it parsed and refuses a
  mismatch before any GitHub or store operation, so an unauthenticated sender
  cannot choose the content identity used for idempotency;
- synchronisation is serialised per feedback session, which makes one issue per
  session a real guarantee for a single gateway replica and is documented as
  exactly that — there is no distributed coordination and none is claimed;
- no CI job requires a real GitHub credential; the GitHub boundary is
  substituted in every test, and a repository invariant fails if a workflow ever
  references a secret;
- the application does not persist IP addresses. The gateway holds a client
  address transiently in memory as a rate-limit key only.

Feedback is not described as anonymous. A learner can type identifying
information into a comment box, hosting and network infrastructure process
metadata this application does not control, and GitHub applies its own
retention. See [LEARNER_FEEDBACK.md](LEARNER_FEEDBACK.md) for the full boundary,
the exact fields collected and excluded, and the claims audit.

## Browser and API controls

- same-origin UI and API; no wildcard CORS;
- strict Pydantic request models with forbidden unexpected fields;
- fixed semantic workbench operations rather than paths or code;
- no learner-controlled HTML rendering;
- no learner file upload;
- Content Security Policy restricted to self/data images;
- frame denial, MIME sniffing protection, no-referrer, restricted browser permissions;
- `Cache-Control: no-store` on API responses;
- API keys omitted from all public schemas;
- React text escaping for structured content;
- clear 404, 422, unavailable, failed, and indeterminate states.

The local SQLite database is not encrypted and is not a credential store. A user with access to
the progress volume can read learner answers and scores.

## Container boundary

The supplied Compose deployment:

- runs the service as an unprivileged user;
- uses a read-only root filesystem;
- drops all Linux capabilities;
- sets `no-new-privileges`;
- binds only to host loopback by default;
- gives write access to the progress volume and isolated `/tmp` only;
- marks `/tmp` `noexec,nosuid`;
- uses pinned runtime images and frozen Python/npm locks.

This is defense in depth for local training, not an independent enforcement boundary for hostile
code. The container still has normal network connectivity so explicitly configured live mode can
work; use an outbound firewall if network denial is required.

## Dependency and supply-chain controls

- exact direct Python and npm versions;
- committed `uv.lock` and `package-lock.json`;
- `uv sync --frozen` and `npm ci --ignore-scripts`;
- framework extras required in full CI;
- adapter conformance run with `--require`;
- no package installation from a learner field;
- Docker build and lock verification gates;
- suspicious-package content in Lab 20 is fixture text and is never executed.

## Reporting a vulnerability

Do not open a public issue for a secret exposure or exploitable vulnerability. Contact the
repository owner privately with the affected version, reproduction, impact, and suggested
mitigation. Do not include real credentials or personal data. Ordinary hardening proposals and
documentation corrections may use a normal issue.

## Out of scope for the initial local release

- authentication, authorization, or multi-user tenancy;
- internet-facing production operation;
- arbitrary learner contracts or code;
- proof of external event truth;
- protection against a hostile host or Docker daemon;
- independent PEP/attestor deployment;
- certification or credential issuance.
