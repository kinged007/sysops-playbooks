# Playbook: WordPress Migration — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`.

## 0. Pre-flight
- [ ] Confirm prerequisites (see README)
- [ ] Read `notes/` for lessons that affect this run
- [ ] Confirm with operator: source is read-only for this run

## 1. Inventory source
- [ ] Record WP version, PHP version, plugins/themes list — `wp core version` on <SOURCE_ALIAS>

## 2. Backup (files + DB)
- [ ] **WRITE** — take full file backup on <SOURCE_ALIAS> (tar to <BACKUP_PATH>)
- [ ] **WRITE** — dump database on <SOURCE_ALIAS> (read-only mysqldump; SELECT only)
- [ ] Verify backup integrity (sizes, checksums) before proceeding

## 3. Transfer
- [ ] **WRITE** — copy backup from <SOURCE_ALIAS> to <DEST_ALIAS> (scp/rsync over SSH keys)
- [ ] Verify transfer (checksums match)

## 4. Restore + reconfigure
- [ ] **WRITE** — extract files on <DEST_ALIAS>
- [ ] **WRITE** — import database on <DEST_ALIAS>
- [ ] **WRITE** — update `wp-config.php` (DB creds, URLs) on <DEST_ALIAS>
- [ ] **WRITE** — apply per-server config (php-fpm, nginx/vhost) on <DEST_ALIAS>

## 5. Verification
- [ ] Site loads on <DEST_ALIAS> (curl homepage, wp-admin login)
- [ ] Check DB consistency (wp core verify-checksums / db check)
- [ ] Confirm with operator before any further production writes

## 6. Rollback
- [ ] If verification fails: point DNS back to <SOURCE_ALIAS>, no changes there were made
- [ ] Document what remains to be cleaned up (backup files) in `notes.md`

---

## Authoring rules
- Steps must be copy-paste executable with placeholders filled.
- Flag every step that WRITES to a production system with **WRITE** in bold.
- Add rollback instructions for every write step.
- After each run, promote lessons into `notes/` (via the operator, never mid-run).
