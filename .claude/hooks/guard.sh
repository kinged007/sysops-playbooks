#!/bin/sh
# PreToolUse hook for Bash. Reads hook JSON on stdin; exit 2 blocks the call.
input=$(cat)
cmd=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null) || exit 0

block() { echo "guard: blocked: $1" >&2; exit 2; }

# Succeeds when a `git commit` invocation in the command carries --no-verify or a -n short flag.
# Only the arguments of the git commit invocation are checked, up to the next ; && || | or newline.
skips_hook() {
  printf '%s' "$cmd" | python3 -c '
import os, re, shlex, sys

SEP = ";()|&\n"
WRAPPERS = {"command", "env", "exec", "sudo", "time", "nohup", "then", "do", "else", "if",
            "while", "until", "!", "{"}
SHELLS = {"sh", "bash", "zsh", "dash", "eval"}
SHORT_WITH_ARG = set("mFCcStu")
LONG_WITH_ARG = ("--message", "--file", "--reuse-message", "--reedit-message")


def tokenize(cmd):
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=SEP)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


def skips(cmd):
    try:
        tokens = tokenize(cmd)
    except ValueError:
        return bool(re.search(r"git\s+commit", cmd) and
                    re.search(r"(^|\s)(--no-v\w*|-[a-zA-Z]*n[a-zA-Z]*)(\s|$)", cmd))
    segments, cur = [], []
    for t in tokens:
        if set(t) <= set(SEP):
            segments.append(cur)
            cur = []
        else:
            cur.append(t)
    segments.append(cur)
    for seg in segments:
        while seg and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", seg[0]) or seg[0] in WRAPPERS):
            seg = seg[1:]
        if seg and os.path.basename(seg[0]) in SHELLS and any(skips(t) for t in seg[1:]):
            return True
        if not seg or os.path.basename(seg[0]) != "git":
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
            elif a == "--no-verify" or (len(a) > 5 and a.startswith("--no-v") and "--no-verify".startswith(a)):
                return True
            elif a.startswith("--"):
                skip = a in LONG_WITH_ARG
            elif a.startswith("-") and len(a) > 1:
                for pos, ch in enumerate(a[1:], 1):
                    if ch == "n":
                        return True
                    if ch in SHORT_WITH_ARG:
                        skip = pos == len(a) - 1
                        break
    return False


sys.exit(0 if skips(sys.stdin.read()) else 1)
'
}

skips_hook && block "git commit with --no-verify or -n skips the pre-commit hook"
printf '%s' "$cmd" | sed 's/git config --get core\.hooksPath//g' | grep -Eq 'core\.hooksPath' && block "changing core.hooksPath"
if printf '%s' "$cmd" | grep -Eq '(^|[;&|(])[[:space:]]*git[[:space:]]+push([[:space:]]|$)'; then
  printf '%s' "$cmd" | grep -Eq '(^|[[:space:]:/+])master([[:space:]]|$)' && block "push to master"
  [ "$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" = master ] && block "push while on master"
fi
exit 0
