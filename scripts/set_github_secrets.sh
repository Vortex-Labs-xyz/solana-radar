#!/usr/bin/env bash
set -euo pipefail
REPO="Vortex-Labs-xyz/solana-radar"
[[ -z "${GH_PAT:-}" ]] && { echo "GH_PAT missing"; exit 1; }
export GH_TOKEN="$GH_PAT"             # gh CLI nutzt GH_TOKEN

while IFS='=' read -r K V; do
  [[ -z "$K" || "$K" =~ ^# ]] && continue
  printf '🔐  %s\n' "$K"
  if ! echo -n "$V" | gh secret set "$K" -R "$REPO" --body - 2>/dev/null; then
    B64=$(printf '%s' "$V" | base64 -w0)
    gh secret set "$K" -R "$REPO" --b64 "$B64"
  fi
done < .env
echo "✅  Secrets synced." 