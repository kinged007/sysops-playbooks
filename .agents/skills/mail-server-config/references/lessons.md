# Lessons learned — mail-server-config

> **Read this file BEFORE any run** (mandatory, AGENTS.md §2/§6). Entries
> flagged `(seed — verify on first run)` are known field-pitfalls included at
> authoring time; they become confirmed lessons once a run hits them. Real
> lessons are appended after runs with the run tag, via the promotion channel
> (run `notes.md` → operator approves → here). Never edit mid-run.

## Seeds (authoring time — verify on first run)

1. **PTR before MX.** Request reverse DNS at the VPS provider BEFORE the
   first MX query. Major receivers tempfail (`450 4.7.1`) mail from IPs
   without matching PTR, and PTR propagation is slow (24–48h).
2. **SPF `permerror`** is almost always record syntax (duplicate `v=spf1`,
   broken mechanism) or >10 DNS lookups — not "the IP is blocked".
3. **DKIM selector/key drift**: after a compose/env change or a migration,
   re-audit the published key against the signing key — a silent
   `dkim=fail` on every message is the classic result.
4. **DNSBL removal lags**: delisting takes 24–48h per list; fix the root
   cause (compromised account / open relay) before requesting removal or the
   listing just returns.
5. **`451 STARTTLS required`** tempfails appear when peers enforce TLS and
   the server's cert is expired/mismatched — check certs before blaming the
   peer.
6. **Quota exceeded (`552`) vs disk-full are different failures** with
   different fixes (raise quota vs free space). Check `df` first.
7. **Back up before any Mailu upgrade** — DB migrations can be one-way.
8. **IMAP migration: target quota must exceed source usage** or the sync
   fails mid-pass with quota errors, leaving a half-copied mailbox.

## Confirmed lessons (from runs — newest first)

### 2026-08-24 `remote-b-mail-server-config-repair` — mailu behind Dokploy/Traefik

1. **HTTP-01 through Traefik is impossible.** Traefik's internal `acme-http` router
   (PathPrefix `/.well-known/acme-challenge/`, priority MAX) 404s every
   challenge path it isn't actively answering — a certbot inside a proxied
   container can never complete HTTP-01. Use **DNS-01** (e.g. certbot +
   Cloudflare plugin) or reuse an existing cert store instead of fighting the
   router.
2. **Compose env interpolation mangles `$` in secrets.** `SECRET_KEY` /
   `INITIAL_ADMIN_PW` containing `$` (e.g. from `tr -dc 'A-Za-z0-9!@#$%^&*'`)
   produce "variable X is not set" warnings and the rendered value is
   silently blanked — a password that "was set" never applies. Generate
   secrets **alphanumeric-only** (base64-style) for compose-managed stacks.
3. **Docker management suites may prefix volume names with the project name**
   (Dokploy, Portainer, Coolify, ...): the compose declares `mailu-certs`
   but the real volume is `mail-server-mailu-2ieime_mailu-certs`. Backup and
   cert-sync scripts must **discover real volume names** (`docker volume ls`
   / `docker inspect`), never assume the compose name — a bare-name volume
   mount silently creates an empty stray volume.
4. **`clamav/clamav-debian` image has no `ps`, `pgrep`, or pid files.**
   Healthchecks must not use `pgrep` or `kill $(cat <pidfile>)`. Use
   `test -S /tmp/clamd.sock` (socket liveness) — clamd creates it at startup
   and removes it on clean shutdown.
5. **Cloudflare-proxied mail subdomains mask untrusted origin certs.**
   Browsers saw Cloudflare's edge cert while the origin served an untrusted
   Cloudflare **origin cert** (wildcard `*.domain` in Traefik custom-certs).
   Grey-clouding the record exposed `SEC_E_UNTRUSTED_ROOT` immediately.
   Audit the origin cert before any grey-cloud/DNS-only change; a real LE
   cert for the exact hostname beats the wildcard (Traefik exact-match
   precedence).
6. **`HOSTNAMES=${DOMAIN}` trap in compose anchors.** Deriving HOSTNAMES from
   DOMAIN breaks the webmail/TLS hostname the moment DOMAIN changes. Always
   set `HOSTNAMES` explicitly (e.g. `mail.<DOMAIN>`) independent of `DOMAIN`.

### 2026-09-28 `mail-server-config-my-tech-mailserver` — fresh Mailu 2024.06 on Dokploy

1. **Absent `PORT_*` keys kill mail ports with no error.** The `front` container
   runs dovecot in proxy mode, and its config is templated as
   `port = {% if PORT_587 %}587{% else %}0{% endif %}` per service. A
   hand-written env without `PORT_587` makes compose publish 587 while
   dovecot binds port 0: connections are refused, and nothing in the
   container logs, the admin UI, or the healthchecks mentions it. Only a
   port-by-port probe from outside the host finds it. Start from the
   rendered wizard env, or set every `PORT_*` you publish. Same trap for
   `PORT_143`/`PORT_110`/`PORT_995`.
2. **`ADMIN=false` is not "off", it is "no admin UI".** The flag gates the
   `location /admin` block in the front nginx template, so setting it to
   false leaves no admin interface at all while the admin container still
   runs and the API still answers internally.
3. **Mailu 2024.06 stores DKIM keys as files, not rows.** There is no `dkim`
   table; keys land in the admin container's `/dkim` volume as
   `<domain>.<selector>.key` and are served to rspamd over
   `http://admin:8080/internal/rspamd/vault`. Generate them with
   `Domain.generate_dkim_key()` + `save_dkim_key()` under an app context —
   the REST route `/api/v1/domain/<d>/dkim` needs `API=true`, which is off
   by default.
4. **Derive the published DKIM TXT with `openssl pkey`, not `openssl rsa`.**
   The key file is PKCS#8 (`BEGIN PRIVATE KEY`), so `openssl rsa -in` fails
   silently and yields an empty `p=`. An empty-p TXT record is worse than
   none: it is published, resolves, and hard-fails DKIM. Check the rendered
   `p=` length before publishing (2048-bit RSA ≈ 392 chars).
5. **Mailu model scripting gotchas.** `mailu.app` and `mailu.db` do not
   exist: use `from mailu import create_app` and `from mailu.models import db,
   User`, and persist with `db.session.add()` + `db.session.commit()` —
   `User.save()` does not exist (`Domain.save_dkim_key()` does).
6. **The resolver (unbound) service is mandatory.** Rspamd aborts at startup
   with "DNSSEC validation required but no resolver configured" without it.
   Give it a fixed address inside the compose subnet and point every mail
   service's `dns:` at it; do not let Docker's embedded resolver answer
   instead.
7. **Mail lands where dovecot's `mail_location` says, not where you guessed.**
   It is `maildir:/mail/%u` — flat, one directory per full address. The
   maildir subdirectories appear on first delivery, so an empty mail root
   right after startup says nothing either way. Verify with
   `doveadm search -u <addr> ALL` rather than by listing the host path.
8. **Postfix logs almost nothing in the Mailu container.** There is no
   syslog and no rsyslog, and only a few master-level lines reach stdout, so
   a missing delivery leaves no log trace. Use `doveadm search` or
   `postqueue -p` for the truth. `postqueue -p` warning "Mail system is down"
   is normal in that container and still prints the queue.
9. **`SQLALCHEMY_DATABASE_URI` is ignored in 2024.06.** With only that set,
   Mailu silently falls back to sqlite. Use `DB_FLAVOR=postgresql` plus
   `DB_HOST` / `DB_USER` / `DB_PW` / `DB_NAME` (and matching `POSTGRES_*`).
10. **Dokploy cannot read a host `env_file`.** It runs compose in an isolated
    project directory and the relative/host `env_file` path is not there, so
    the stack starts with missing settings. Pass the whole environment as a
    compose `environment:` anchor — that is what survives.
11. **Cloudflare tokens fail per zone, not per account.** A token with the
    right account can still 403 on one zone's writes (`Authentication
    error`, code 10000) while reading that same zone fine. The account id
    in a screenshot is not the permission set; `Zone / Zone / Read` +
    `Zone / DNS / Edit` are required for `POST /zones/<id>/dns_records`.
    Test writes early, before building anything that depends on DNS.
12. **Two SPF records on one name is a permerror, not a merge.** Publishing
    SPF for a domain that already has one (a forwarding service, an old
    provider) makes every send fail. Always list existing records first,
    then fold the old mechanisms into the single new record. An SPF
    permerror is silent: the API returns 200 for the new record, and
    nothing fails until mail is rejected downstream.
13. **Traefik's docker provider issues one certificate per SAN.** A service
    that must present the same cert for several hostnames cannot get it
    from labels. The file provider can:
    `tls: {certResolver: letsencrypt, domains: [{main: a, sans: [b]}]}`.
    Store it in the watched dynamic-config directory; it applies without a
    Traefik restart.
14. **A backend that redirects http→https must not be proxied on :80.**
    Traefik on 443 → backend :80 → 301 to https → Traefik :80 again is an
    infinite redirect loop that shows up as 301/308 with no error anywhere.
    Point the load balancer at the backend's own TLS port.
15. **Traefik verifies the backend certificate against the URL host.** With
    `url: https://front:443` and a cert for `mail.example`, every request
    fails 500 with `x509: certificate is valid for ...`. Fix with a
    `serversTransports` entry setting `serverName` to a name the cert
    covers, rather than `insecureSkipVerify: true`.
16. **Dokploy's `/api/domain.create` writes a database row and nothing
    else** — no Traefik router, no certificate. It looks successful and
    routes nowhere. For a raw compose, declare routing yourself.
17. **Traefik's `acme.json` base64-encodes its PEM values.** Reading
    `certificate`/`key` as text gives base64 gibberish, and a chain lookup
    written against it finds nothing. Decode first. Note the key is only
    in that store, which is why Mailu's cert is copied out of it rather
    than issued separately.
18. **`openssl verify` on a multi-certificate file reports failure.** It
    verifies only the first certificate. Split the file and verify with
    `-untrusted <intermediates> <leaf>` to prove a chain is complete.
