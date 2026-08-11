# Playbook: Mail Server Configuration — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`.

## 0. Pre-flight
- [ ] Confirm prerequisites (see README)
- [ ] Read `notes/` for lessons that affect this run

## 1. Baseline inventory
- [ ] Record MTA, version, current config state on <MAIL_ALIAS> (reads only)

## 2. DNS records (SPF/DKIM/DMARC)
- [ ] **WRITE** — add/update SPF record (TXT at <DOMAIN>) — via DNS provider
- [ ] **WRITE** — add/update DKIM record (TXT at <DKIM_SELECTOR>._domainkey.<DOMAIN>) — via DNS provider
- [ ] **WRITE** — add/update DMARC record (TXT at _dmarc.<DOMAIN>) — via DNS provider
- [ ] Verify DNS propagation (dig / nslookup) before MTA changes

## 3. MTA configuration
- [ ] **WRITE** — apply MTA config changes on <MAIL_ALIAS> (main.cf / postfix, exim conf, etc.)
- [ ] **WRITE** — restart mail service on <MAIL_ALIAS>

## 4. Relay/auth
- [ ] **WRITE** — configure relay host / SMTP auth on <MAIL_ALIAS>

## 5. Verification (send test mail)
- [ ] Send test mail from <MAIL_ALIAS> to <TEST_RECIPIENT>
- [ ] Confirm delivery + DKIM/SPF/DMARC pass (headers, e.g. mail-tester.com)
- [ ] Check mail logs for errors on <MAIL_ALIAS>

## 6. Rollback
- [ ] If delivery fails: revert config (backup taken before changes) and restart service
- [ ] Document remaining issues in `notes.md`

---

## Authoring rules
- Steps must be copy-paste executable with placeholders filled.
- Flag every step that WRITES to a production system with **WRITE** in bold.
- Add rollback instructions for every write step.
- After each run, promote lessons into `notes/` (via the operator, never mid-run).
