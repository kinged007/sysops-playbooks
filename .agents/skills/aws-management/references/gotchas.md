# Gotchas — AWS Management

Read this before any run. Append new lessons after each execution (operator
approves promotion, never mid-run).

## G1 — IAM actions are `ses:*`, not `sesv2:*`

SES API v2 actions still use the `ses:` prefix (e.g. `ses:CreateEmailIdentity`,
`ses:GetEmailIdentity`). A policy with `sesv2:CreateEmailIdentity` is silently
ignored — `SimulatePrincipalPolicy` returns `implicitDeny` with no error.
**Impact:** `VerifyDomainDkim` / `DeleteIdentity` / `CreateEmailIdentity`
requests all `AccessDenied` until the prefix is fixed. **Fix:** list them as
`ses:*` in `templates/playbook-ses-policy.json` (see commit `bdb39f1`). Always
verify with `aws iam simulate-principal-policy --policy-source-arn <ARN> --action-names ses:VerifyDomainDkim ...`.

## G2 — `playbook-automation` cannot self-elevate its own policy

A least-privilege automation user lacking `iam:CreatePolicyVersion` /
`iam:PutUserPolicy` cannot patch `SES-Agent` itself. **Impact:** DKIM enable +
stale-identity delete stay blocked. **Fix:** patch `SES-Agent` once from
Console (IAM → Policies → SES-Agent → New version, add
`ses:VerifyDomainDkim`, `ses:SetIdentityDkimEnabled`, `ses:DeleteIdentity`,
`ses:CreateEmailIdentity`, `ses:DeleteEmailIdentity`, `ses:GetEmailIdentity`,
`ses:ListEmailIdentities`) and set as default. Management user stays narrow;
send-only user should be separate.

## G3 — SES DKIM CNAMEs must not clash with existing mail provider

If the domain's MX is on another provider (e.g. Migadu) with its own
`key1/2/3._domainkey` CNAMEs, SES Easy DKIM generates *random* tokens like
`oe7qo…._domainkey` — separate labels, so both providers coexist. **Check:**
`GET /zones/<id>/dns_records?type=CNAME` before writing, and pick TTL 300
proxied false for SES records. Never replace existing keys; SPF must be
*merged* (`include:amazonses.com` added to `v=spf1 include:spf.migadu.com -all`)
not replaced, or migadu mail fails SPF.

## G4 — `aws ses send-email` CLI syntax changed

AWS CLI v2.38 uses `--from` / `--to` / `--subject` / `--text` (not
`--source` / `--destination`). `sesv2 send-email` uses
`--from-email-address` + `--destination` JSON + `--content` JSON. Check
`aws ses send-email help` on the host version before scripting. The old
`--source` form now errors `ParamValidation: --from is required`.

## G5 — DoH negative cache hides fresh Cloudflare TXT briefly

Right after `POST /dns_records` for `_amazonses`, Cloudflare DoH may return
`Status 3` (NXDOMAIN) for a few seconds due to negative cache, while the
direct `GET /dns_records?name=_amazonses...` already shows the record. SES
`get-identity-verification-attributes` polled `Pending→Success` in ~60s anyway.
**Tip:** verify via both `https://cloudflare-dns.com/dns-query` and
`https://dns.google/resolve` before concluding failure; also retry DKIM poll —
SES needs both DNS propagation *and* its own verifier.

## G6 — Cross-variant Cloudflare token: read in place, never copy

`executions/mail-server-config-my-tech-mailserver/secrets/cf-dns-01.ini`
holds the same `my-tech.uk` zone. Per AGENTS.md §1.4 reuse within a variant
unless explicit cross-variant approval: the SES run records operator-approved
read-only use of that file (path `executions/mail-server-config-…/secrets/…`),
never copies the token, and notes the zone id `f2c28…` only partially.

## G7 — SES is regional; verify in the same region you send from

`my-tech.uk` was verified only in `eu-west-1` (where the token was created).
Verification in `us-east-1` etc. shows `VerificationAttributes: {}`.
Always pair `--region eu-west-1` on every `verify-*`, `get-*`, and `send-email`
call, and store the region in `inventory.md` + `~/.aws/config`.

## G8 — Stale identity cleanup needs `ses:DeleteIdentity`

Deleting `digitalsorcery.io` after it was replaced required `ses:DeleteIdentity`
(classic) + `ses:DeleteEmailIdentity` (v2). Without those, `AccessDenied`.
Delete only *after* the new domain shows
`VerificationStatus Success` / `SendingEnabled true` / `DkimVerificationStatus Success`.

## G9 — Domain no longer owned must be removed from inventory

`digitalsorcery.io` stayed in `inventory.md` / `list-identities` as `FAILED`
long after it was unowned. The SES run now removes it from both and records
the replacement in notes; keep `inventory.md`'s Domain field current.

## G10 — Send-only credentials should be a separate user

`playbook-automation` has `ses:Verify*`, `ses:Delete*`, `iam:List*` etc. for
management. Applications that only *send* should use a different IAM user
(e.g. `ses-sender`) with only `ses:SendEmail` / `ses:SendRawEmail` scoped to
the domain resource — never reuse the management keys.

## G11 — Custom MAIL FROM (bounce.my-tech.uk) needs two DNS + one SES call

SPF alignment strict requires `bounce.my-tech.uk` MX →
`feedback-smtp.eu-west-1.amazonses.com` + TXT
`v=spf1 include:amazonses.com -all`, then
`aws ses set-identity-mail-from-domain --identity <DOMAIN>
 --mail-from-domain bounce.<DOMAIN>` (needs
`ses:SetIdentityMailFromDomain`). Without it envelope is
`@amazonses.com` and DMARC alignment stays relaxed. DNS shows via CF
`GET` immediately but DoH `Status 3` for a minute due to negative cache.
