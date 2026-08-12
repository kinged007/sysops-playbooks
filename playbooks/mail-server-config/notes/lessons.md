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

*(None yet. After a run: `## YYYY-MM-DD <run tag> — <one-line summary>`, then
bulleted lessons.)*
