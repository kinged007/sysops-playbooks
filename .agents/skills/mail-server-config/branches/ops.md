# Branch: Ops — Lifecycle, Maintenance & Security

> **Loaded by the master playbook (D1 = ops).** Maintenance of a deployed
> Mailu server (or any Mailu stack this playbook set up). Read-only by
> default; every **WRITE** flagged with rollback. Runs against <MAIL_ALIAS>
> per the execution's plan.md.

**Goal:** keep the mail server backed up, patched, monitored, and secure —
and know exactly how to bring it back when something breaks.

---

## 1. Backup

- [ ] **WRITE — Run a backup**: `scripts/backup-mailu.sh <MAIL_ALIAS>
      <BACKUP_DEST>` — DB dump + maildir + compose/env, archived, pulled
      off-box, verified (`tar tzf` count + `gzip -t`). Additive only.
      Rollback: none (additive).
- [ ] **Schedule it**: cron on the operator machine (or a backup host) —
      daily DB+config, weekly full maildir (adjust to mail volume):
      ```cron
      15 2 * * *  <BACKUP_CMD>   # example daily run; adapt paths
      ```
- [ ] **Verify the backup**: `tar tzf <ARCHIVE> | head` and `gzip -t`
      pass; spot-extract the DB dump and confirm it opens.
- [ ] **Restore drill** (quarterly, or per policy): actually run §2 restore
      into a THROWAWAY stack (second compose dir on the same host or a test
      host) — proves the backup before it's needed. Record the drill date
      and result in `notes.md`.

## 2. Restore

> **WRITE — OVERWRITES live mail data.** Requires explicit operator
> approval; permission mode applies (AGENTS.md §1.3).

- [ ] Pre-flight: `scripts/restore-mailu.sh <MAIL_ALIAS> <BACKUP_PATH>` —
      script asserts the stack is down (`docker compose down`) before
      restoring, then: restore DB dump (sqlite file or pg dump), extract
      maildir into the volume with Mailu's UID/GID (`chown -R 5000:5000` —
      check the image's user in `docker-compose.yml`), restore
      compose/env, `docker compose up -d`.
- [ ] Verify: `docker compose ps` healthy; common.md §2 TLS + §3 SMTP
      battery; a restored mailbox shows the expected message count.
- [ ] Rollback: restore the PRE-restore state from the backup taken just
      before this restore (backup → restore → verify → if broken, restore
      again from the pre-restore archive).

## 3. Updates

- [ ] **WRITE — Backup FIRST** (always, §1): Mailu DB migrations can be
      one-way (seeded lesson #7).
- [ ] **WRITE — Upgrade**: in `<MAILU_DIR>`:
      `docker compose pull` (check release notes for config changes first);
      `docker compose up -d`; `docker compose ps` all healthy.
- [ ] Verify after: common.md §2/§3 spot checks; webmail + admin login.
- [ ] Rollback: restore previous compose + env from the pre-upgrade backup
      and re-run restore (§2), or `docker compose down` + redeploy previous
      images pinned in git history of `<MAILU_DIR>`.

## 4. Certificates

- [ ] Expiry check (common.md §2.3): `echo | openssl s_client -connect
      <SERVER_IP>:465 -servername mail.<DOMAIN> 2>/dev/null | openssl x509
      -noout -enddate` — renew if < 14 days (Mailu Traefik renews
      automatically; check `docker logs mailu-front` for renewal errors).
- [ ] Set an alert: calendar/cron that runs the expiry check weekly.

## 5. Monitoring

- [ ] Health: `docker compose ps` — any container not `healthy`/`running`
      → investigate (repair.md §4.11).
- [ ] Queue: `docker exec mailu-smtp postqueue -p | tail -3` — >10 deferred
      for >1h → repair.md §4.9.
- [ ] Disk: `df -h <MAIL_VOLUME_PATH>` — <20% free → repair.md §4.12.
- [ ] fail2ban: `docker exec mailu-front fail2ban-client status` — growing
      ban counts → brute force (§6 below).
- [ ] Log scan: `docker logs mailu-smtp --since 24h | grep -icE
      'rejected|error'` — weekly trend recorded in `notes.md`.

## 6. Security review (quarterly checklist)

- [ ] Firewall re-audit: `ufw status` (or provider security group) — only
      25/465/587/143/993/80/443 public; SSH restricted.
- [ ] Open ports from outside: `nc -zv <SERVER_IP> <PORT>` sweep — nothing
      unexpected listening.
- [ ] fail2ban jails active + ban list reviewed (`fail2ban-client status
      <JAIL>`); unban only with cause.
- [ ] Admin access review: admin UI user list — stale accounts removed.
- [ ] 2FA confirmed on all admin accounts.
- [ ] Credential rotation: secrets referenced in `mailu.env` rotated on a
      policy schedule; rotation = generate new → update env → restart stack
      (rollback: restore old env).
- [ ] Patching: OS updates (`apt update && apt upgrade` — **WRITE**,
      requires plan approval) and Mailu image bumps (§3).

## 7. Account lifecycle (WRITE per action)

- [ ] **Create user**: admin UI → Users → create (or CLI per setup.md §4);
      quota set per policy. Rollback: delete user (only after backing up
      their maildir if live).
- [ ] **Disable user**: admin UI → disable. Rollback: re-enable.
- [ ] **Delete user** (operator-approved only): disable first, back up
      maildir, then delete. Rollback: restore from backup.
- [ ] **Aliases / forwarding / catch-all**: admin UI → Aliases; document
      changes in `notes.md`. Rollback: delete the alias.

## 8. Storage management

- [ ] Disk trend: `df -h` + per-maildir growth
      (`du -sh <MAIL_VOLUME>/*` per user) recorded monthly.
- [ ] Quota reports: `docker exec mailu-imap doveadm quota get -A` — users
      at >90% flagged for the operator (repair.md §4.6).
- [ ] Archive/cleanup policy: define with the operator (e.g. archive users
      >X months inactive to off-box storage); deletion of maildirs is
      operator-approved only.
- [ ] Log rotation: docker log limits in compose
      (`logging: driver: json-file, options: max-size/max-file`) — verify
      configured; unbounded logs = disk-full risk (repair.md §4.12).

## 9. Close-out

- [ ] Findings recorded in `notes.md`; promotion candidates → operator
      (→ `notes/lessons.md`).
