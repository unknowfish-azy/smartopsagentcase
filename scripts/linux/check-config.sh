#!/usr/bin/env bash
set -u

status_required() {
  local name="$1"
  if [[ -n "${!name:-}" ]]; then printf 'OK'; else printf 'MISSING'; fi
}

status_optional() {
  local name="$1"
  if [[ -n "${!name:-}" ]]; then printf 'OK'; else printf 'OPTIONAL'; fi
}

printf '%-12s %s\n' 'MySQL' "$(status_required MYSQL_PASSWORD)"
printf '%-12s %s\n' 'Redis' "$(status_optional REDIS_PASSWORD)"
printf '%-12s %s\n' 'LLM' "$(status_required LLM_PROVIDER)"
printf '%-12s %s\n' 'Encryption' "$(status_required SMARTOPS_API_KEY_ENCRYPTION_KEY)"
printf '%-12s %s\n' 'Internal' "$(status_required SMARTOPS_INTERNAL_TOKEN)"
printf '%-12s %s\n' 'Knowledge' "$(status_required KNOWLEDGE_SERVICE_URL)"

for name in MYSQL_PASSWORD LLM_PROVIDER SMARTOPS_API_KEY_ENCRYPTION_KEY SMARTOPS_INTERNAL_TOKEN KNOWLEDGE_SERVICE_URL; do
  [[ -n "${!name:-}" ]] || exit 1
done
