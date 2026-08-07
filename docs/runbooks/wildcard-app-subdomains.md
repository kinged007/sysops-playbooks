# Runbook: Wildcard App Subdomains for Coder Previews

How Coder's **workspace app previews**
(`https://3000--main--<workspace>--<user>.coder.<domain>`) are exposed through
Dokploy + Traefik, and how to make them actually work (routing **and** TLS).
This is the knowledge gained when the preview URLs returned Traefik's
`404 page not found` and an invalid certificate.

> Replace `<domain>` (e.g. `example.com`), `<user>`, `<ORIGIN_PUBLIC_IP>`, and
> the Coder app name with your real values. Real fleet values stay in
> gitignored `secrets/` + `servers/`.

**TL;DR — the two things that must both be right:**
1. **Routing** — Traefik must match `*.coder.<domain>` with a `HostRegexp`
   rule (Dokploy's domain UI can't do this).
2. **TLS** — Traefik must serve a **wildcard** cert for `*.coder.<domain>`,
   issued via **DNS-01** (HTTP-01 cannot issue wildcards).

---

## 1. How the pieces fit together

```
 browser
   │  https://3000--main--<workspace>--<user>.coder.<domain>
   ▼
 coder.<domain>  ──► Cloudflare proxy (orange cloud)
   │                 TLS terminated by Cloudflare edge
   ▼
 *.coder.<domain> ──► <ORIGIN_PUBLIC_IP> (origin, DNS-only / grey cloud)
                       TLS terminated by Dokploy's Traefik
                       ▼
                       Traefik ─► Coder (internal port 7080)
                                     ▼
                                     workspace app on port 3000
```

### DNS split — intentional, do not "fix" it
- `coder.<domain>` → **Cloudflare** (proxied). Cloudflare terminates TLS with
  its own edge cert, so the dashboard works even though the origin serves
  Traefik's default cert.
- `*.coder.<domain>` → **origin IP directly** (DNS-only). This is the *only*
  option because:
  - Cloudflare will not proxy wildcard (`*`) DNS records — wildcards must be
    grey-cloud.
  - Cloudflare Universal SSL covers `*.<domain>` (one level) but **not**
    `*.coder.<domain>` (two levels), so Cloudflare can't hand you a valid cert
    for it anyway.

The two hostnames resolving to different targets is correct and required.

---

## 2. Coder side (server config)

Set in the Coder deployment env (Dokploy compose for the Coder app):

```dotenv
CODER_ACCESS_URL=https://coder.<domain>
CODER_WILDCARD_ACCESS_URL=*.coder.<domain>
CODER_HTTP_ADDRESS=0.0.0.0:7080
```

Coder only *generates* app URLs of the form
`<port>--<agent>--<workspace>--<user>.coder.<domain>` when the wildcard access
URL is set. If you can see such a URL in the Coder UI, this side is correct.
Nothing else to do here.

---

## 3. Reverse proxy (Dokploy/Traefik) — routing

### The trap
Dokploy wraps every domain you enter as `Host(\`<host>\`)`
(`packages/server/src/utils/docker/domain.ts`). Traefik's `Host()` matcher does
**exact** hostname comparison only (`pkg/muxer/http/matcher.go`:
`reqHost == host`). So `Host(\`*.coder.<domain>\`)` never matches real
subdomains — the request falls through to Traefik's default cert + `404 page
not found`. **There is no way to express a working wildcard rule through
Dokploy's Domains UI.**

### The fix — a HostRegexp router via compose labels
1. In the Coder app → **Domains**, delete the `*.coder.<domain>` entry
   (keep `coder.<domain>`).
2. In the Coder app → **compose editor**, add these labels to the `coder`
   service (user-authored labels survive Dokploy redeploys):
   ```yaml
   labels:
     - traefik.http.routers.coder-wildcard-web.rule=HostRegexp(`^[a-z0-9-]+\.coder\.<domain>$`)
     - traefik.http.routers.coder-wildcard-web.entrypoints=web
     - traefik.http.routers.coder-wildcard-web.service=coder-wildcard-web
     - traefik.http.routers.coder-wildcard-web.middlewares=redirect-to-https@file
     - traefik.http.services.coder-wildcard-web.loadbalancer.server.port=7080
     - traefik.http.routers.coder-wildcard-websecure.rule=HostRegexp(`^[a-z0-9-]+\.coder\.<domain>$`)
     - traefik.http.routers.coder-wildcard-websecure.entrypoints=websecure
     - traefik.http.routers.coder-wildcard-websecure.service=coder-wildcard-websecure
     - traefik.http.services.coder-wildcard-websecure.loadbalancer.server.port=7080
     - traefik.http.routers.coder-wildcard-websecure.tls=true
   ```
3. **Deploy.**

Notes:
- `port=7080` is Coder's internal HTTP port (`CODER_HTTP_ADDRESS`).
- `tls=true` (not `certresolver`) so Traefik serves the wildcard cert from its
  store instead of trying to ACME-issue per hostname (it can't — the rule is a
  regex, Traefik can't extract a domain from it).
- Keep the router/service names unique and unrelated to Dokploy's generated
  names (e.g. `coder-wildcard-*`) so Dokploy never collides with them.

---

## 4. TLS — the wildcard certificate

### The trap
Dokploy's Traefik `letsencrypt` resolver only has an `httpChallenge`
(`/etc/dokploy/traefik/traefik.yml`). Let's Encrypt **cannot issue wildcard
certs over HTTP-01** — wildcards require **DNS-01**. So no wildcard cert ever
lands in the ACME store, and Dokploy's custom-cert dir
(`/etc/dokploy/traefik/dynamic/certificates/`) is empty → Traefik serves its
self-signed `TRAEFIK DEFAULT CERT`. A "Let's Encrypt" setting in the Dokploy
domain UI validates DNS, it does **not** produce a wildcard cert.

### The fix — acme.sh + Cloudflare DNS-01 into Dokploy's cert dir
Script: `scripts/setup-wildcard-cert.sh` (run as root on the Coder host):

```bash
ssh <alias>
sudo bash /tmp/setup-wildcard-cert.sh     # token file: /home/<user>/.cf-token
```

Prereqs:
- Cloudflare **API token** with `Zone → DNS → Edit` for `<domain>`, saved to
  `/home/<user>/.cf-token` (or `$CF_Token` env).
- The token must **not** be IP-restricted (acme.sh runs from the host, not your
  workstation).
- Tokens expire (max TTL typically 1 year) — use the longest TTL and plan to
  rotate before expiry, or the first auto-renewal breaks.

What it does:
1. Installs acme.sh as root (so the renewal cron runs as root).
2. Issues `*.coder.<domain>` via the `dns_cf` plugin (creates/removes the
   `_acme-challenge` TXT record automatically).
3. Writes `chain.crt`, `privkey.key`, and `certificate.yml` into
   `/etc/dokploy/traefik/dynamic/certificates/wildcard-coder/`.
4. Traefik's file provider (watch: true) picks them up automatically — no reload
   needed.

`certificate.yml` (Dokploy's file-provider layout; Traefik mounts the dynamic
dir at the same path):
```yaml
tls:
  certificates:
    - certFile: /etc/dokploy/traefik/dynamic/certificates/wildcard-coder/chain.crt
      keyFile: /etc/dokploy/traefik/dynamic/certificates/wildcard-coder/privkey.key
```

### Token lifecycle / renewal
- LE certs last 90 days; acme.sh's cron re-issues at ~60 days and re-applies the
  install, so renewal is automatic **as long as the Cloudflare token is still
  valid at renewal time**.
- When you rotate the token, update **two** places on the host:
  `/home/<user>/.cf-token` **and** acme.sh's cached copy in
  `/root/.acme.sh/*.coder.<domain>/*.coder.<domain>.conf`
  (acme.sh uses its cached `CF_Token` for renewals, not the file).

---

## 5. Verification

From any machine:

```bash
# 1. TLS — cert served must be the wildcard (subjectAltName DNS:*.coder.<domain>)
echo | openssl s_client -connect <ORIGIN_PUBLIC_IP>:443 \
  -servername anything.coder.<domain> 2>/dev/null \
  | openssl x509 -noout -subject -ext subjectAltName

# 2. Routing — must return Coder's response, NOT Traefik's "404 page not found"
curl -sk https://3000--main--<workspace>--<user>.coder.<domain>/

# 3. Traefik actually forwarded it (origin status != 0)
ssh <alias> "grep 3000--main--<workspace>--<user> \
  /etc/dokploy/traefik/dynamic/access.log | tail -1"
```

### Troubleshooting table

| Symptom | Cause | Fix |
|---|---|---|
| `404 page not found`, self-signed cert | No router matches the app hostname | `HostRegexp` rule (§3); confirm `OriginStatus != 0` in access log |
| Valid cert in Dokploy UI but browser says invalid | Cert was never served (empty cert dir, HTTP-01-only resolver) | Issue via DNS-01 (§4) |
| `Host(\`*\`)` router present but never matches | Traefik `Host()` is exact-match only | Use `HostRegexp` (§3) |
| acme.sh: token rejected | Token IP-restricted, or zone lacks `DNS:Edit` | Recreate token, no IP restriction, scope `<domain>` |
| Renewal fails silently | Token expired between renewals | Long-TTL token; update `/home/<user>/.cf-token` + acme.sh cache (§4) |
