# DNS records reference — canonical table for a mail server on <DOMAIN>
# at IP <SERVER_IP>, hostname mail.<DOMAIN>. Fill placeholders per run;
# verify each with scripts/dns-audit.sh (branches/common.md §1).
# Every row is a WRITE at the DNS provider (or VPS panel for PTR).

| Record | Type | Name | Value | TTL | Notes |
|---|---|---|---|---|---|
| MX | MX | `<DOMAIN>` | `10 mail.<DOMAIN>` | 3600 | Lower to 300 before cutover (migrate branch) |
| SPF | TXT | `<DOMAIN>` | `v=spf1 mx ip4:<SERVER_IP> -all` | 3600 | One record only; keep < 10 lookups |
| DKIM | TXT | `<SELECTOR>._domainkey.<DOMAIN>` | `v=DKIM1; k=rsa; p=<PUBLIC_KEY>` | 3600 | Key generated on the server; default selector `dkim` |
| DMARC | TXT | `_dmarc.<DOMAIN>` | `v=DMARC1; p=quarantine; rua=mailto:<POSTMASTER>@<DOMAIN>; ruf=mailto:<POSTMASTER>@<DOMAIN>` | 3600 | Tighten to `p=reject` after stable (ops.md) |
| PTR | PTR | `<SERVER_IP_REV>.in-addr.arpa` | `mail.<DOMAIN>` | n/a | Set at VPS provider panel, NOT registrar |
| autoconfig | A | `autoconfig.<DOMAIN>` | `<SERVER_IP>` | 3600 | Auto-config XML served by the front |
| autodiscover | SRV | `_autodiscover._tcp.<DOMAIN>` | `0 0 443 mail.<DOMAIN>` | 3600 | Outlook auto-discovery |
| MTA-STS | TXT | `_mta-sts.<DOMAIN>` | `v=STSv1; id=<YYYYMMDD>` | 3600 | Bump id on every policy change |
| MTA-STS policy | HTTPS | `https://mta-sts.<DOMAIN>/.well-known/mta-sts.txt` | `v=STSv1; mode=enforce; mx: mail.<DOMAIN>; max_age=604800` | n/a | Requires `mta-sts.<DOMAIN>` A → `<SERVER_IP>` |

## Propagation

- Verify from multiple resolvers: `dig @8.8.8.8 +short MX <DOMAIN>` and
  `dig @1.1.1.1 +short MX <DOMAIN>`.
- Respect the TTL: a change published at TTL 3600 takes up to an hour to be
  seen consistently; PTR can take 24–48h.
- Never assume propagation — the common.md DNS audit is the gate.

## Typical mistakes

- SPF with two `v=spf1` records → permerror (repair.md §4.2)
- DKIM published key ≠ server signing key → silent dkim=fail (repair.md §4.3)
- PTR set at the registrar instead of the VPS panel → never works
- MX pointing at a CNAME target → not RFC-compliant, receivers may reject
