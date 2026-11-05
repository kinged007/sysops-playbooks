#!/usr/bin/env python3
"""migadu-api.py — authenticated Migadu API helper (read-only unless told).

Reads credentials from files so the API key never appears on a command line,
in shell history, or in logs. Only the HTTP status and the JSON body are
printed; the Authorization header and any password fields are never echoed.

Usage:
    migadu-api.py <user-file> <key-env-file> <METHOD> <path> [body.json]

    <user-file>     file holding the Migadu account email (Basic-auth user)
    <key-env-file>  file with one line: MIGADU_API_KEY=<key>
    <METHOD>        GET, POST, PATCH, PUT, DELETE
    <path>          e.g. /domains/<DOMAIN>/mailboxes
    [body.json]     JSON file for POST/PATCH/PUT (omit for GET/DELETE)

Examples (placeholders from the run's plan.md):
    migadu-api.py secrets/migadu_user.txt <KEY_ENV> GET /domains/<DOMAIN>
    migadu-api.py secrets/migadu_user.txt <KEY_ENV> POST /domains/<DOMAIN>/mailboxes newbox.json

Exit 0 on HTTP 2xx, 1 otherwise.
"""

import base64
import json
import sys
import urllib.request
import urllib.error

REDACT = {"password"}


def fail(msg):
    print(f"migadu-api.py: {msg}", file=sys.stderr)
    sys.exit(2)


def main():
    if len(sys.argv) < 4:
        fail("usage: migadu-api.py <user-file> <key-env-file> <METHOD> <path> [body.json]")
    user_file, key_file, method, path = sys.argv[1:5]
    body_file = sys.argv[5] if len(sys.argv) > 5 else None

    try:
        user = open(user_file).read().strip()
    except OSError as e:
        fail(f"cannot read user file: {e}")
    key = None
    try:
        for line in open(key_file):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == "MIGADU_API_KEY":
                    key = v.strip().strip("\"'")
    except OSError as e:
        fail(f"cannot read key file: {e}")
    if not user or not key:
        fail("missing account email or MIGADU_API_KEY")

    data = None
    if body_file:
        try:
            data = open(body_file, "rb").read()
        except OSError as e:
            fail(f"cannot read body file: {e}")

    token = base64.b64encode(f"{user}:{key}".encode()).decode()
    req = urllib.request.Request(
        f"https://api.migadu.com/v1{path}",
        data=data,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, payload = resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        status, payload = e.code, e.read().decode()
    print(f"HTTP {status}")
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        print(payload[:2000])
    else:
        if isinstance(obj, dict):
            obj = {k: ("<redacted>" if k in REDACT else v) for k, v in obj.items()}
        print(json.dumps(obj, indent=1)[:4000])
    sys.exit(0 if 200 <= status < 300 else 1)


if __name__ == "__main__":
    main()
