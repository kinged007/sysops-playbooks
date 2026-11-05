#!/bin/sh
# PreToolUse hook for Bash. Reads hook JSON on stdin; exit 2 blocks the call.
input=$(cat)
cmd=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null) || exit 0

block() { echo "guard: blocked: $1" >&2; exit 2; }

# Succeeds when a `git commit` invocation in the command carries --no-verify or a -n short flag.
# Only the arguments of the git commit invocation are checked, up to the next ; && || | or newline.
skips_hook() {
  printf '%s' "$cmd" | python3 -c '
import re, shlex, sys

cmd = sys.stdin.read()
SEP = ";()|&\n"
lex = shlex.shlex(cmd, posix=True, punctuation_chars=SEP)
lex.whitespace = " \t\r"
lex.whitespace_split = True
lex.commenters = ""
try:
    tokens = list(lex)
except ValueError:
    found = re.search(r"git\s+commit", cmd) and re.search(r"(^|\s)(--no-verify|-[a-zA-Z]*n[a-zA-Z]*)(\s|$)", cmd)
    sys.exit(0 if found else 1)

segments, cur = [], []
for t in tokens:
    if set(t) <= set(SEP):
        segments.append(cur)
        cur = []
    else:
        cur.append(t)
segments.append(cur)

SHORT_WITH_ARG = set("mFCcStu")
LONG_WITH_ARG = ("--message", "--file", "--reuse-message", "--reedit-message")
for seg in segments:
    while seg and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", seg[0]):
        seg = seg[1:]
    if not seg or seg[0] != "git":
        continue
    i = 1
    while i < len(seg) and seg[i].startswith("-"):
        i += 2 if seg[i] in ("-c", "-C") else 1
    if i >= len(seg) or seg[i] != "commit":
        continue
    skip = False
    for a in seg[i + 1:]:
        if skip:
            skip = False
        elif a == "--no-verify":
            sys.exit(0)
        elif a.startswith("--"):
            skip = a in LONG_WITH_ARG
        elif a.startswith("-") and len(a) > 1:
            for pos, ch in enumerate(a[1:], 1):
                if ch == "n":
                    sys.exit(0)
                if ch in SHORT_WITH_ARG:
                    skip = pos == len(a) - 1
                    break
sys.exit(1)
'
}

skips_hook && block "git commit with --no-verify or -n skips the pre-commit hook"
printf '%s' "$cmd" | grep -Eq 'core\.hooksPath' && block "changing core.hooksPath"
if printf '%s' "$cmd" | grep -Eq '(^|[;&|(])[[:space:]]*git[[:space:]]+push([[:space:]]|$)'; then
  printf '%s' "$cmd" | grep -Eq '(^|[[:space:]:/+])master([[:space:]]|$)' && block "push to master"
  [ "$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" = master ] && block "push while on master"
fi
exit 0
