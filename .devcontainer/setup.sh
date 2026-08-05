#!/usr/bin/env bash
# Devcontainer / Codespaces bootstrap.
#
# Goal: from "Open in Codespaces" to a working `nornyx-lab` prompt, with nothing
# left for the learner to install and no lab that skips.
set -euo pipefail

echo "── Installing uv ──────────────────────────────────────────────"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "── Creating the environment ───────────────────────────────────"
uv venv
# Both framework extras are installed deliberately: without them labs 18-20
# skip, the suite reports green, and the gate asserts nothing (Ch. 15).
uv pip install -e ".[dev,crewai,langgraph,notebooks]"

# Put the venv on PATH for every future shell in this container.
VENV_LINE='export PATH="/workspaces/nornyx-lab/.venv/bin:$HOME/.local/bin:$PATH"'
grep -qxF "$VENV_LINE" ~/.bashrc || echo "$VENV_LINE" >> ~/.bashrc

echo "── Building the contracts ─────────────────────────────────────"
.venv/bin/python scripts/build_contracts.py

echo "── Checking the environment ───────────────────────────────────"
.venv/bin/nornyx-lab doctor

cat <<'EOF'

  Ready.

    nornyx-lab            your dashboard
    nornyx-lab next       start the next lab
    nornyx-lab list       all 25 labs

EOF
