# Branch: Setup — Fresh Mail Server Install (Mailu on Docker)

> **Loaded by the master playbook (D1 = fresh install). Also load
> `branches/common.md` — verification checkpoints below call it.** Worked
> example: **Mailu** (all-in-one Docker mail suite: Postfix MTA, Dovecot MDA,
> rspamd antispam, ClamAV, Roundcube webmail, admin UI, Traefik TLS). DNS
> knowledge applies to any stack — the components are universal.

**Goal:** a secured, correctly-configured mail server accepting and sending
mail for `<DOMAIN>`, with spam/virus protection, working webmail and admin
UI, provisioned storage, and a baseline backup.

Scale (from discovery D2): **small** → SQLite backend; **medium/large** →
PostgreSQL backend. Pick the matching compose template.

---

## 0. Pre-flight (reads — no changes)

- [ ] Read `notes/lessons.md` — mandatory before any run.
- [ ] Confirm access + permission mode in `plan.md` (AGENTS.md §1.3).
- [ ] Hostname check on <MAIL_ALIAS> (all below run via `ssh <MAIL_ALIAS>`):
      `hostname -f` → must be a FQDN like `mail.<DOMAIN>`. A bare hostname
      breaks rDNS alignment and TLS.
- [ ] IPv4 and IPv6 present: `ip -4 addr`, `ip -6 addr`. (No IPv6 is OK but
      record it — some receivers prefer AAAA.)
- [ ] Ports reachable from the internet (from the operator machine):
      `nc -zv <SERVER_IP> 25 465 587 143 993 80 443` — all must be open in
      the firewall/provider security group.
- [ ] Docker engine installed + running: `docker --version`, `docker ps`.
      If absent → STOP, this is a deviation (plan doesn't cover installing
      Docker; ask operator).
- [ ] **WRITE — Place the PTR request NOW** at the VPS provider panel:
      reverse DNS for `<SERVER_IP>` → `mail.<DOMAIN>`. Do this **before**
      cutover: PTR propagates slowly and major receivers tempfail mail from
      IPs without matching PTR. Rollback: none needed (reversible at panel).
- [ ] Disk: `df -h` on the volume that will hold mail. Budget:
      mailboxes × quota × 1.5 headroom, e.g. 10 users × 5 GB = 50 GB + 25 GB.
      Less than budget → STOP, ask operator.

## 1. Deploy Mailu (WRITE)

> All files land on the server under `<MAILU_DIR>` (e.g. `/opt/mailu`).
> Create it with `mkdir -p` — then every subsequent step is in that dir.

- [ ] **WRITE** — Copy `templates/mailu-compose.yml` (small) or
      `templates/mailu-compose-postgres.yml` (medium/large) →
      `<MAILU_DIR>/docker-compose.yml`, and `templates/mailu.env` →
      `<MAILU_DIR>/mailu.env`. Fill every placeholder from `plan.md`.
      **Secrets** (`SECRET_KEY`, `DB_PASSWORD`, `ADMIN_PASSWORD`,
      `RSPAMD_PASSWORD`) are generated fresh for this run and stored in the
      execution `secrets/` folder — never inline. Rollback: files are new;
      nothing is live yet.
      - `DOMAIN=<DOMAIN>`, `HOSTNAMES=mail.<DOMAIN>` (comma-list for extra
        hostnames)
      - `TLS_FLAVOR=letsencrypt` (or `cert` if a manual cert is provided)
        and `LETSENCRYPT_EMAIL=<POSTMASTER>`
      - `ANTIVIRUS=true` (ClamAV), `WEBMAIL=roundcube`
      - small: `DB_FLAVOR=sqlite`; medium/large: `DB_FLAVOR=postgresql` +
        DB host/user/pass set
- [ ] **WRITE** — Storage: the maildir lives in the `mailu` Docker volume
      (named `<MAILU_DIR>-mailu` or as defined in compose). Record the volume
      name; sizing decided in §0. No further action needed unless a
      dedicated disk/partition is planned — then mount it at the volume path
      BEFORE first start (docs: Docker named volumes → bind mount). Rollback:
      unmount / rename volume before any mail exists.
- [ ] **WRITE** — Start the stack:
      `docker compose up -d` (from `<MAILU_DIR>`); then
      `docker compose ps` — every container `healthy`/`running`. Check logs:
      `docker compose logs --tail=50` for errors. Rollback: `docker compose
      down` (fresh install, no data loss).
- [ ] **WRITE** — Create the admin account (password from run `secrets/`):
      `docker exec mailu-admin flask mailu admin <ADMIN_USER> <ADMIN_PASSWORD>`.
      Enable **2FA (TOTP)** on it in the admin UI before proceeding
      (security baseline). Rollback: `docker exec mailu-admin flask mailu
      admin --remove <ADMIN_USER>` if miscreated.

## 2. DNS phase (WRITE at the DNS provider — every record is a WRITE)

> Use `templates/dns-records.md` as the reference table. Create records in
> this order, verifying each with the common.md DNS audit before the next.

- [ ] **WRITE** — **MX**: `mail.<DOMAIN>` MX 10. Verify: `dig +short MX <DOMAIN>`.
      Rollback: delete the MX record.
- [ ] **WRITE** — **SPF**: TXT at `<DOMAIN>`:
      `v=spf1 mx ip4:<SERVER_IP> -all`. Verify syntax via common.md §1.2.
      Rollback: delete/revert TXT.
- [ ] **WRITE** — **DKIM**: generate keys in the admin UI (domain →
      *generate DKIM keys*) — note the selector shown (default `dkim`).
      Publish the resulting TXT at `<SELECTOR>._domainkey.<DOMAIN>`. Verify:
      common.md §1.3 — published key must match the server's key. Rollback:
      delete TXT; keep keys (regenerating breaks signed mail).
- [ ] **WRITE** — **DMARC**: TXT at `_dmarc.<DOMAIN>`:
      `v=DMARC1; p=quarantine; rua=mailto:<POSTMASTER>; ruf=mailto:<POSTMASTER>`.
      After 2–4 weeks of clean reports, tighten to `p=reject` (ops.md).
      Rollback: delete/revert TXT.
- [ ] **WRITE** — **autodiscover/autoconfig** (recommended, makes clients
      configure themselves): `autoconfig.<DOMAIN>` A → `<SERVER_IP>`;
      `_autodiscover._tcp.<DOMAIN>` SRV `0 0 443 mail.<DOMAIN>`. Mailu serves
      the config XML automatically. Rollback: delete records.
- [ ] **WRITE** — **MTA-STS** (optional, recommended once stable):
      TXT `_mta-sts.<DOMAIN>` = `v=STSv1; id=<YYYYMMDD>` + policy file at
      `https://mta-sts.<DOMAIN>/.well-known/mta-sts.txt`
      (`v=STSv1; mode=enforce; mx: mail.<DOMAIN>; max_age=604800`).
      Rollback: remove TXT + policy file.
- [ ] Run the full **DNS audit** (common.md §1) and **wait out the TTL**
      (`dig` TTL on the MX) before continuing — DNS change lag is the #1
      "why is my mail broken" cause.

## 3. Post-deploy verification

- [ ] **TLS audit** (common.md §2): ports 25/465/587/143/993 reachable;
      STARTTLS works on 587/143; Let's Encrypt cert issued (container
      `mailu-front` logs show cert creation); cert expiry > 14 days.
- [ ] **SMTP test battery** (common.md §3):
      - send to external test address → received, headers show
        `spf=pass`, `dkim=pass`, `dmarc=pass` (common.md §3.4)
      - send to self → lands in local mailbox
      - receive from external (gmail/outlook) → arrives, not in spam
- [ ] Webmail login (Roundcube at `https://mail.<DOMAIN>`) with a test user.
- [ ] Admin UI login (`https://mail.<DOMAIN>/admin`) with 2FA.
- [ ] Any FAIL → fix via the repair branch catalog (branches/repair.md §4)
      before proceeding. Do not hand over a server that fails verification.

## 4. Account provisioning (WRITE)

- [ ] **Domains**: add `<DOMAIN>` in admin UI → *Domains* (alias domains as
      needed). Rollback: remove domain only after users are handled.
- [ ] **Quota policy** (D6): set a per-user default quota in admin UI
      (e.g. 5 GB). Total quota across users must fit the §0 disk budget.
- [ ] **Users**: create each account (admin UI or
      `docker exec mailu-admin flask mailu user create <USER>@<DOMAIN>
      <PASSWORD>`); enforce a password policy (≥12 chars, no reuse).
      Rollback: `flask mailu user delete <USER>@<DOMAIN>` (removes maildir —
      back up first if the user is live).
- [ ] **Aliases** (optional): admin UI → *Aliases* (e.g. `info@` → real
      users). Rollback: delete alias.
- [ ] **Catch-all**: decide per domain; OFF by default (spam magnet).
      If ON, document why in plan.md. Rollback: remove catch-all alias.
- [ ] **Disabled-account policy**: create a documented process — disable
      (not delete) accounts on departure, retain maildir per retention
      policy; delete only after operator approval + backup.

## 5. Hardening (WRITE)

- [ ] **Firewall** on <MAIL_ALIAS>: allow only 25, 465, 587, 143, 993, 80,
      443 from the internet; restrict 22 (SSH) to operator IPs if possible.
      (UFW example below — adapt to the distro; **test the SSH rule LAST**
      and from a second session so you don't lock yourself out.)
      ```bash
      ufw allow 25,465,587,143,993,80,443/tcp
      ufw allow from <OPERATOR_IP> to any port 22
      ufw enable
      ```
      Rollback: `ufw delete allow <rule>` / `ufw disable`.
- [ ] **fail2ban**: Mailu bundles it (front container) — verify jails:
      `docker exec mailu-front fail2ban-client status` (jails: postfix-sasl,
      postfix, dovecot, admin, nginx-http-auth). Any jail stopped → recheck
      container health. Rollback: n/a (service state).
- [ ] **Admin 2FA** — already enforced in §1; spot-check `mailu-admin` logs
      for repeated failed logins.
- [ ] **Plaintext auth**: Mailu requires TLS before auth on 587/143 by
      default — verify no auth accepted on a plain connection (common.md §2.2
      handshake must fail without STARTTLS for auth). 
- [ ] **Rate limits**: rspamd rate limit plugin — confirm default limits
      sane in admin UI (avoid lockout of your own bulk sends; tighten after
      a week of use).

## 6. Handover

- [ ] **WRITE — Baseline backup NOW**: run the ops.md backup procedure
      (`scripts/backup-mailu.sh <MAIL_ALIAS> <BACKUP_DEST>`) so the first
      backup exists before the server is in production.
- [ ] Credentials summary → execution `secrets/` (never in runbook.md).
- [ ] Record in `notes.md`: versions (Mailu, compose, OS), volume names,
      DNS record table, quota policy, anything unusual.
- [ ] Handover checklist for the operator: webmail URL, admin URL, backup
      schedule, monitoring suggestions (ops.md).

---

**Authoring rules:** every **WRITE** above has a rollback. Deviations from
this plan → STOP and ask (AGENTS.md §1.4). After the run, promote findings
to `notes/lessons.md` via the operator.
