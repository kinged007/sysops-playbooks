#!/bin/sh
# PreToolUse hook for Bash. Reads hook JSON on stdin; exit 2 blocks the call.
cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null) || exit 0

block() { echo "guard: blocked: $1" >&2; exit 2; }

if echo "$cmd" | grep -Eq '(^|[;&|(])[[:space:]]*git[[:space:]]+commit([[:space:]]|$)'; then
  echo "$cmd" | grep -Eq '(^|[[:space:]])(--no-verify|-[a-zA-Z]*n[a-zA-Z]*)([[:space:]]|$)' &&
    block "git commit with --no-verify or -n skips the pre-commit hook"
fi
echo "$cmd" | grep -Eq 'core\.hooksPath' && block "changing core.hooksPath"
if echo "$cmd" | grep -Eq '(^|[;&|(])[[:space:]]*git[[:space:]]+push([[:space:]]|$)'; then
  echo "$cmd" | grep -Eq '(^|[[:space:]:/+])master([[:space:]]|$)' && block "push to master"
  [ "$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" = master ] && block "push while on master"
fi
exit 0
