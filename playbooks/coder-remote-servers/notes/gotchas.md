# Gotchas (G1–G12) — Coder Remote Servers

Real pitfalls hit on the fleet, with fixes. Read BEFORE any run (mandated by
README).

**G1 — dind server cert doesn't include the tailnet IP.**
Symptom: `tls: failed to verify certificate: x509: certificate is valid for
10.0.2.2, 127.0.0.1, ::1, not <ts-ip>`. Cause: dind generates its server cert
SAN at startup from container-detected IPs unless told otherwise. **Fix:
`DOCKER_TLS_SAN: "IP:<ts-ip>"` in the compose, then recreate the container.**
Certs regenerate on every start (CA persists in its volume).

**G2 — broken third-party dnf/yum repos break installers.**
On Rocky/CentOS, a stale repo (we hit netdata) 404s during metadata refresh and
kills `curl | sh` installers. Fix: disable it first:
```bash
dnf config-manager --set-disabled netdata netdata-repoconfig
dnf install -y --disablerepo='netdata*' tailscale
```
**Netdata root cause (corrected 2026-08-11):** the 404 was NOT a dead repo —
netdata's `.repo` file uses `$releasever_major` in `baseurl`, which dnf 4.14 on
Rocky 9 does not substitute (built-in only since dnf 4.21), so the literal
`$releasever_major` went to the server. Fix that survives repo-file updates:
```bash
echo 9 > /etc/dnf/vars/releasever_major   # generic dnf var substitution, works in 4.14
dnf config-manager --set-enabled netdata netdata-repoconfig
```
(`--setopt=releasever_major=9` does NOT work — only the vars file does.)
Also: Tailscale's `install.sh` may die before adding the repo on RHEL-family.
Add it manually: `dnf config-manager --add-repo https://pkgs.tailscale.com/stable/rhel/9/tailscale.repo`.

**G3 — Coolify renames the container.**
Coolify deploys the compose with a suffixed container name
(`workspace-docker-dgkmftx...`). Any `docker exec workspace-docker` fails with
"no such container". Use `name=$(docker ps -aq --filter name=workspace-docker | head -1)`.

**G4 — port conflict on redeploy.**
If the agent creates/validates the container via SSH and the user then redeploys
via Coolify, the port `ts-ip:2376` is still held → "port is already allocated".
**Always remove the agent-created container before a Coolify redeploy**
(`docker rm -f <name>`), then have the user redeploy so Coolify owns it.

**G5 — `/root` is often unreadable for the sudo user.**
Staging certs under `/root/coder-tls/` fails with "Permission denied" for user.
Use a user-writable path: `/home/<user>/coder-tls/<remote>/`.

**G6 — `coder templates push --var` breaks with multiline PEM.**
`--var docker_ca="$(cat ca.pem)"` mangles multi-line content through the shell.
Use `--variables-file <file>`. **Coder's variables file is YAML, not tfvars:**
```yaml
docker_host: tcp://<ts-ip>:2376
docker_ca: |
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----
```

**G7 — Windows PowerShell array interpolation joins with SPACES.**
Building the YAML in PowerShell via `"$(...)"` collapsed PEM lines into one
space-separated line → "tls: failed to find any PEM data". Fix: build a
`List[string]` and `-join "`n"` (real newlines), then write the file.

**G8 — Tailscale policy: grants syntax ≠ legacy ACL syntax.**
`autogroup:member:41641` fails with "host name must not contain colon". In
`grants`, ports live in the `ip` field (`tcp:22`, `icmp:*`), never appended to
`dst`. 41641 is auto-allowed. Replacing the policy drops default SSH — re-add if needed.

**G12 — Tailscale API ACL updates: use POST, never an empty body.**
Updating the policy file via the API is `POST /api/v2/tailnet/<tailnet>/acl`
(`PUT` returns 405). **A POST with an empty/malformed body can reset the policy
to the default allow-all** — we hit this live and had to restore immediately.
Always: GET the current policy, edit it, and POST the full content back with
`Content-Type: application/hujson`; verify with a follow-up GET. Scope required
is `policy_file`. Fetch the tailnet name from the host's
`tailscale status --json` (`MagicDNSSuffix`, e.g. `tailcXXXX.ts.net`).
The key can be stored in gitignored `executions/<run>/secrets/`.

**G9 — Coder CLI session expires.** `coder whoami` → "signed out". User runs
`coder login <url>` (browser). The CLI URL is stored in the coderv2 config; check
it before blaming a wrong URL.

**G10 — dind image tag.** Use a **current** `docker:dind` tag (e.g. `29.7.1-dind`).
Older pins in docs (e.g. `29.6.2-dind`) may not exist — verify against Docker Hub
before deploying.

**G11 — Windows → remote script execution.**
Piping a script into `ssh ... bash -s` from PowerShell re-encodes newlines to
CRLF and breaks bash. Write the script with LF endings and `scp` it, then run
`bash /tmp/script.sh`. Also: PowerShell interpolates `$()` in double-quoted ssh
commands **locally** — use single quotes or script files for anything with
`$(...)`.
