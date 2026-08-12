# Branch: Migrate — Mailbox Migration into a New Mailu Server

> **Loaded by the master playbook (D1 = migrate). Also load
> `branches/common.md`.** **Requires:** target Mailu deployed and verified
> (setup.md §1–3 completed). Source = any server with IMAP access. This is a
> **WRITE-heavy** branch — every cutover step needs explicit approval.

**Goal:** move mailboxes from the source server to the target Mailu with
zero message loss, a defined rollback (MX flip-back), and verification at
every stage.

**Strategy:** copy mailboxes via **IMAP sync** (imapsync) while the source
keeps receiving mail; verify counts; then flip **MX/DNS**, run a final
**delta pass**, verify again, and let both run in parallel until the
operator decommissions the source.

---

## 1. Pre-flight

- [ ] Read `notes/lessons.md` (mandatory).
- [ ] Source stack + access documented in the inventory (D3): IMAP server
      (host/port/SSL), per-account credentials **or** admin access to export
      credentials; source protocol limits (imapsync rate, concurrent
      connections).
- [ ] Target confirmed: setup.md §1–3 done, common.md battery passes on the
      target.
- [ ] **WRITE — Lower DNS TTL 24–48h BEFORE cutover**: set the TTL of the
      MX record to 300s (5 min) at the DNS provider. Verify:
      `dig +short MX <DOMAIN>` and read the TTL. Rollback: restore original
      TTL.
- [ ] **Delta budget agreed with operator**: acceptable window between the
      final delta pass and the MX flip (a few minutes at most — plan for
      ~5 min).
- [ ] Mailbox manifest: list all accounts on the source with usage
      (`du`-equivalent: IMAP folder sizes / provider report). Target quota
      per account must EXCEED source usage, or the sync fails mid-pass
      (seeded lesson #8).

## 2. Provision targets (WRITE — setup.md §4 pattern)

- [ ] Add the domain(s) on the target (admin UI).
- [ ] Create each user with quota > source usage; record the mapping
      source-account → target-account in the runbook.
- [ ] Mirror aliases and forwarding rules.
- [ ] Rollback for this phase: delete the mirrored users (setup.md §4
      rollback) — nothing live yet.

## 3. Copy mailboxes (WRITE — additive on the target)

- [ ] **Dry-run one account first**: `scripts/migrate-mailboxes.sh --source
      <SRC_IMAP> --target <TGT_IMAP> --account <USER> --dry-run` — confirms
      credentials, IMAP versions, and folder mapping before any writes.
      Log: `logs/03-dry-run-<USER>.log`.
- [ ] **Full pass, one account at a time**:
      `scripts/migrate-mailboxes.sh --source <SRC_IMAP> --target <TGT_IMAP>
      --account <USER>`
      (manual fallback:
      `imapsync --host1 <SRC_HOST> --user1 <USER> --passwordfile
      <SRC_CREDS> --host2 <TGT_HOST> --user2 <USER> --passwordfile
      <TGT_CREDS> --syncinternaldates`).
      Per-account log in `logs/03-full-<USER>.log`.
- [ ] **Verify per account**: folder list and message counts on target vs
      source (imapsync report summary; spot-check the newest message in the
      largest folder).
- [ ] Check target logs for sync errors:
      `docker logs mailu-imap --since <START_TIME> | grep -iE 'error|fail'`.
- [ ] Rollback: a partial/bad account sync is rolled back by deleting that
      user on the target (setup.md §4) and re-syncing — never delete on the
      source.

## 4. DNS cutover (WRITE)

- [ ] Operator go/no-go: all accounts synced and verified, delta budget
      agreed.
- [ ] **Final delta pass** (only mail received since §3):
      `scripts/migrate-mailboxes.sh ... --delta` for every account. Note the
      timestamp of completion — this is the cutover instant.
- [ ] **WRITE — Flip MX**: point `<DOMAIN>` MX at `mail.<DOMAIN>` (the
      target), TTL 300. Rollback: **MX flip-back** to the source MX — valid
      until the source is decommissioned.
- [ ] **WRITE — Update SPF** if it references the source IP:
      change `ip4:<SRC_IP>` → `ip4:<TGT_IP>` in the SPF TXT. Rollback:
      revert SPF.
- [ ] **WRITE — PTR on the target IP** if not already set (setup.md §0):
      `<TGT_IP>` → `mail.<DOMAIN>` at the VPS provider. Rollback: remove PTR.
- [ ] Propagate: wait out the 300s TTL; verify via common.md §1 (multi
      resolver).

## 5. Post-cutover verification & close

- [ ] common.md §3 battery against the target: send to external, send to
      self, receive from external — headers `spf=pass dkim=pass dmarc=pass`
      (common.md §3.4).
- [ ] **WRITE — Second delta pass** 15–30 min after the flip (catches mail
      that arrived during propagation), then verify counts again.
- [ ] Test a client: configure a fresh mailbox in Thunderbird/Outlook with
      autodiscover (setup.md §2) — send + receive.
- [ ] **Parallel run**: leave the source receiving for 48–72h (MX is on the
      target now; source just accumulates). Operator then:
- [ ] **WRITE — Decommission source** (operator-owned, separate approval):
      stop services, update/remove old DNS (MX/SPF/PTR references), archive
      a final backup of the source maildirs.
- [ ] Rollback during the whole window: MX flip-back + SPF revert + (if
      needed) delta-sync back to source. After decommission, rollback is
      restore-from-backup only (ops.md restore procedure).
- [ ] Record findings in `notes.md`; propose lessons to `notes/lessons.md`.

---

**Authoring rules:** every **WRITE** has a rollback; source is NEVER
modified except by operator decommission; deviations → STOP + ask.
