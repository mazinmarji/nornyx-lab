# Feedback gateway provisioning

Deployment support for the [feedback gateway](../../gateway/README.md). This
directory provisions infrastructure; it makes no claim that a gateway is
serving anywhere — see the deployment-status section of
[`docs/LEARNER_FEEDBACK.md`](../../docs/LEARNER_FEEDBACK.md), which stays
authoritative until H1-D hosted acceptance completes.

## Target topology

```
Internet HTTPS
      ↓
single gateway replica            replicas = 1 is a correctness bound,
      ↓                           not a sizing choice (one issue per
persistent /var/lib/nornyx-feedback   session is a per-process guarantee)
      ↓
private GitHub intake repository  mazinmarji/nornyx-lab-feedback
```

Runtime configuration is non-secret except `NORNYX_FEEDBACK_GITHUB_TOKEN`,
which exists only in the platform's runtime secret store. Values:
[`production.env.template`](production.env.template).

## Hosting selection

Requirements: Docker deployment, public HTTPS, runtime secret injection, a
persistent volume, one fixed replica with no forced autoscaling, low
operational complexity.

No pre-authenticated hosting authority existed in the provisioning
environment (no cloud CLI, no kubectl context, no tunnel daemon), so the
package targets **Fly.io** as the lowest-complexity platform satisfying all
six requirements: Dockerfile-native deploys, `*.fly.dev` TLS at the edge,
`flyctl secrets` runtime injection, first-class volumes, and a machine
count that is pinned (`scale count 1`, `--ha=false`, volume-bound) rather
than autoscaled. Alternatives were rejected on requirements, not taste:
free-tier Render has no persistent disk, Koyeb free has no volumes, and a
laptop tunnel has no stable hostname and no uptime story.

[`compose.production.yaml`](compose.production.yaml) carries the identical
topology for any plain Docker host behind a TLS-terminating proxy, and is
what the staging rehearsal runs.

## Provision on Fly.io

```bash
flyctl auth login          # human step 1: hosting authority
bash ops/feedback-gateway/deploy_fly.sh
```

The script is idempotent: app, volume, deploy, single-machine pin, the
topology verifier, then a **live credential smoke** — all against the live
endpoint. On first run it pauses and tells you exactly which
**fine-grained** GitHub token to mint (human step 2: `Issues: Read and
write` on the intake repository only, nothing else) and stores it straight
into Fly's secret store with echo disabled. The token never enters a file,
a build argument, an image layer, or this repository.

## Live credential smoke

`/health` reporting `github_configured=true` proves a token is *present*,
not that it works. `scripts/smoke_h1d_gateway.py` proves the deployed
gateway can execute the boundary it was provisioned for, through its real
production API and schema:

```
synthetic session UUID
  → POST valid synthetic payload through the deployed HTTPS gateway
  → expect `created`
  → fetch the resulting issue independently (operator gh authority,
    not the credential under test) and prove: intended intake repo,
    raw UUID absent, sha256(UUID) marker present, exactly one issue
  → identical resubmit → `unchanged`, same issue
  → one field changed, digest recomputed → `updated`, same issue
  → close the synthetic issue
```

Any 401/403/404/422/5xx from the gateway, duplicate creation, a wrong
repository, or an unidentifiable issue exits non-zero and aborts the
deploy script before it can report the provisioning ready. This is not
learner acceptance: no consent flow, no UI, no database-loss recovery, no
revocation, no claim change — only proof the new credential works.

Payload digests are recomputed with a stdlib canonicalisation whose
fidelity is pre-flighted against the committed golden Academy payload, so
canonicalisation drift aborts the smoke instead of surfacing as a
confusing 422.

## Staging rehearsal on any Docker host

```bash
export NORNYX_FEEDBACK_GITHUB_REPOSITORY=mazinmarji/nornyx-lab-feedback
export NORNYX_FEEDBACK_DESTINATION_VISIBILITY=private
export NORNYX_FEEDBACK_GITHUB_TOKEN=...   # from a secret store; never a file
docker compose -f ops/feedback-gateway/compose.production.yaml up -d
```

`NORNYX_FEEDBACK_BIND_PORT` (default 8080) moves the loopback bind when
8080 is taken. The compose file binds loopback only: plain HTTP must never
face the internet, so a real docker-host deployment puts a TLS-terminating
reverse proxy in front.

## Verify — never trust the deploy command

```bash
python scripts/verify_h1d_provisioning.py --self-test   # negative controls
python scripts/smoke_h1d_gateway.py --self-test         # smoke-checker negative controls
python scripts/verify_h1d_provisioning.py \
  --repository mazinmarji/nornyx-lab-feedback --expect-visibility private \
  --endpoint https://<host> \
  --fly-config ops/feedback-gateway/fly.toml \
  --compose-file ops/feedback-gateway/compose.production.yaml \
  --container nornyx-feedback-gateway \
  --scan-tree .
```

The verifier asks GitHub for the repository's actual visibility, checks TLS
and `/health` honesty, pins one replica and the volume target in both
configurations and in the running container, and scans tracked files,
image history, logs, and the gateway database for credential-shaped
content. `--self-test` proves every one of those checks can fail, by
feeding each a broken fixture (no volume, two replicas, a public repository
claimed private, a planted token) that must be rejected.

## Restart persistence

An ordinary restart must not be an empty-store recovery. The rehearsal
proof: sync one session, `docker compose restart` (and separately `down`
without `-v` + `up`), then resubmit the identical payload — the gateway
must answer `unchanged`, which it can only do if
`/var/lib/nornyx-feedback/gateway.db` survived. Deliberate database loss is
**not** part of provisioning; recovery-from-loss belongs to H1-D acceptance.
