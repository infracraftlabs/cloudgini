#!/usr/bin/env bash
# Creates .env for local development: a random database password and four API keys
# (viewer, analyst, operator, admin). Only SHA-256 hashes of the keys go into .env;
# the keys themselves are printed ONCE here. Save them in your password manager.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env && "${1:-}" != "--force" ]]; then
  echo ".env already exists. Use --force to replace it (all old keys stop working)." >&2
  exit 1
fi
rand() { openssl rand -hex 24; }
hash() { printf '%s' "$1" | shasum -a 256 | cut -d' ' -f1; }
entries=()
echo "Local CloudGini API keys (shown once):"
for role in viewer analyst operator admin; do
  key="cg_${role}_$(rand)"
  entries+=("${role}:${role}:$(hash "$key")")
  printf '  %-8s %s\n' "$role" "$key"
done
umask 077
{
  echo "POSTGRES_PASSWORD=$(rand)"
  echo "CLOUDGINI_API_KEYS=$(IFS=,; echo "${entries[*]}")"
  echo "# CLOUDGINI_GCP_PROJECTS=my-demo-project"
  echo "# CLOUDGINI_GCP_BILLING_TABLE=my-billing-project.billing_export.gcp_billing_export_resource_v1_XXXXXX"
  echo "# ANTHROPIC_API_KEY="
} > .env
echo "Wrote .env (hashes only). Next: docker compose up --build"
