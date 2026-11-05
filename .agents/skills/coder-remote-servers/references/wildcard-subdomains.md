# Wildcard App Subdomains — Traps and Fixes

Lessons from the old runbook `docs/runbooks/wildcard-app-subdomains.md`
(now §10 of playbook.md). Read BEFORE any run that touches Coder app previews.

- **Trap 1 — Dokploy UI cannot express wildcard rules.** Dokploy wraps domains
  as `Host(\`...\`)`, and Traefik's `Host()` is exact-match. `Host(\`*.coder.<domain>\`)`
  never matches. Fix: `HostRegexp` router via compose labels
  (`traefik.http.routers.coder-wildcard-websecure.rule=HostRegexp(\`^[a-z0-9-]+\.coder\.<domain>$\`)`,
  entrypoint websecure, `tls=true` not a certresolver, service port 7080).
- **Trap 2 — no wildcard cert possible via Dokploy's ACME.** Dokploy's
  letsencrypt resolver is HTTP-01 only; wildcards require DNS-01. Fix:
  `scripts/setup-wildcard-cert.sh` (acme.sh + Cloudflare DNS-01) installing
  into `/etc/dokploy/traefik/dynamic/certificates/` — Traefik's file provider
  picks it up, no reload.
- **Trap 3 — DNS split is intentional.** `coder.<domain>` → Cloudflare proxied;
  `*.coder.<domain>` → origin IP DNS-only (Cloudflare can't proxy wildcards and
  can't issue certs for two-level wildcards). Do not "fix" this.
- **Trap 4 — token renewal.** LE certs renew at ~60 days; acme.sh uses its
  cached `CF_Token`. Rotating the token means updating BOTH
  `/home/<user>/.cf-token` and `/root/.acme.sh/...conf`. Use non-IP-restricted
  tokens with longest TTL.
- **Verification:** `openssl s_client -connect <ip>:443 -servername anything.coder.<domain>`
  must show the wildcard SAN; `curl -sk` the preview URL must NOT return
  Traefik's "404 page not found".
