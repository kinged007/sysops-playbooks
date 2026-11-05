# Lessons learned — migadu-mailserver

> **Read this file BEFORE any run** (mandatory). Entries flagged
> `(seed — verify on first run)` are known pitfalls included at authoring
> time; they become confirmed lessons once a run hits them. Real lessons are
> appended after runs with the run tag, via the promotion channel
> (run `notes.md` → operator approves → here). Never edit mid-run.

## Seeds (authoring time — verify on first run)

1. **Two SPF records on one name is a permerror, not a merge.** Always list
   existing TXT records first, then fold old mechanisms into one record.
2. **Activate only after diagnostics pass.** `GET …/activate` 422s on bad
   DNS; the fix is DNS, not retries.
3. **Invitation vs password.** `password_method: invitation` needs a
   `password_recovery_email` and the owner sets their own secret;
   `password` sets it immediately and must be stored in run `secrets/`
   (mode 600) before the call.
4. **Mailbox delete is irreversible.** Disable first, back up (IMAP export
   or provider retention confirmed with the operator), delete only on
   explicit approval.

## Confirmed (from runs — newest first)

### 2026-11-05 `migadu-mailserver-munyard` — create blocked account-side

1. **Check `usage`/verification before promising a mailbox.** Create on a
   limited account fails `403 "mailbox limit reached for unverified
   accounts, please contact support!"` — an account-tier refusal, not a
   credential problem. Reads (SHOW/INDEX) still return 200 on the same key,
   so "reads work" does not prove "writes work".
2. **Mailbox INDEX returns `{"mailboxes": [...]}`**, not a bare list; SHOW
   on a missing local part returns 404 with `{"error": "no such mailbox:
   <local>"}` — 404 pre-create is the expected green light.
3. **A vanished self-hosted stack + MX pointing at Migadu means the domain
   migrated.** Confirm with the operator before touching the old stack —
   the Mailu data left behind is history, not the live system.
4. **API keys are per user, not per domain.** Record whose user owns the key
   in `inventory.md`; per-client segregation still applies (never reuse
   another client's token).

### 2026-11-02 `migadu-allroundsound` — domain onboard (DNS only)

1. **The standard Migadu DNS set is 13 records**: verification TXT, 2× MX,
   SPF TXT, 3× DKIM CNAMEs, DMARC TXT, autoconfig CNAME, 4× SRV (per the
   `GET …/records` response — save it, never retype values).
2. **Clean up the stale records in the same run**: the pre-Migadu MX and
   any old DKIM TXT must go, or mail and signing stay broken. Leave web
   A/AAAA and `_acme-challenge` untouched.
3. **Verify via an independent path** (DoH for every record) plus the
   Migadu dashboard green, which only the operator can confirm.
4. **Mailbox creation stayed operator-side** in that run (domain added and
   mailbox confirmed by the operator in admin UI) — the API path (§2
   create) is the alternative when a key is available.
