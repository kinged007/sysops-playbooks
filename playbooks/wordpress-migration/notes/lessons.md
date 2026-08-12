# Lessons Learned — WordPress Migration

Verified incidents from real runs. Read BEFORE any run. Each entry names the
playbook section it anchors to. Items marked **(2026-08, 2026-08 first run)**
were hit live during the first full execution and promoted to the playbook.

## L1 — Charset corruption: always pass `--default-character-set` on dump
**(2026-08, 2026-08 first run — first import was silently corrupted)**

Symptom: pages show `??` where non-ASCII characters (e.g. non-breaking
spaces `\xC2\xA0`) should be. Cause: source server default
`character_set_server=latin1`; `mysqldump` without an explicit charset
follows the latin1 default and corrupts multibyte sequences in the dump
file. The source renders fine — corruption only surfaces on the destination.

Fix (anchors playbook §5.1):
```bash
wp db export /tmp/site.sql --add-drop-table --single-transaction --quick \
  --default-character-set=utf8 --hex-blob
```
Verify the dump round-trips (hex-compare a known multibyte sample) before
importing. Combine with `--hex-blob` for binary columns (Wordfence
`binary(16)` IP columns otherwise fail imports with `Duplicate entry`).

## L2 — `uploads` must be 755, not 750, when nginx and PHP are different users
**(2026-08, 2026-08 first run — every upload returned 403)**

`chmod 750` denies "others", and nginx (running as a different user than
php-fpm) gets `13: Permission denied` on traversal → HTTP 403 on all
uploads. In a split-user container setup (nginx→php-fpm), use **755** — PHP
keeps write access via *ownership*, nginx reads as "others". Only use 750
when web server and PHP share a group. (Anchors playbook §4.5.)

## L3 — Exclude `wp-config.php` from EVERY rsync, including `--delete` deltas
**(2026-08, 2026-08 first run — two incidents at cutover)**

- A delta re-sync overwrote the destination's customized `wp-config.php`
  (dest DB host/creds/salts) with the source's → DB connection broke until
  config was re-applied.
- Worse: with `--delete` on a mirror→volume sync, the destination's
  `wp-config.php` was **deleted entirely** (site 500 until rebuilt).

Rules:
- Exclude `wp-config.php` from the initial transfer, the stage→volume copy,
  AND the final delta sync — same exclude list everywhere.
- Never let `--delete` remove it from the destination volume.
- Record the exclusion in the run's inventory. (Anchors playbook §4.1,
  risk register #24.)

## L4 — `wp search-replace --precise --recurse-objects` skips unloaded classes
**(2026-08, 2026-08 first run — staging)**

Serialized objects of unloaded plugin classes (MailChimp, WPML, WCML,
Freemius, …) are skipped with only a `Skipping an uninitialized class`
warning — old strings remain in plugin cache/settings. Not front-end
content, and correct again once the domain reverts at cutover, so usually
acceptable. To fix at staging, load the plugin classes first (run the
replace with that plugin active). (Anchors playbook §5.4.)

## L5 — Double-escaped URLs evade search-replace
**(2026-08, 2026-08 first run — staging)**

JSON-escaped slashes (`\u005c` forms) in a few `post_content` rows evade
both URL replaces and `wp search-replace`. Fix per-row with a bare
`REPLACE(col, 'old', 'new')` **limited to plain-text columns only** — never
on serialized columns (`postmeta.meta_value`, `options.option_value`).
(Anchors playbook §5.4.)

## L6 — Stale object cache after DB re-import → silent broken behavior
**(2026-08, 2026-08 first run — my-account login broken after cutover)**

After a DB re-import, a file object cache (W3TC) held a stale `alloptions`
snapshot taken while the options table was mid-rebuild → `get_option()`
returned empty/wrong values even though the DB was correct. A custom plugin
reading that option then misbehaved (ran its installer on every request,
redirect-looping logins).

Rules:
- Purge the object cache (`rm -rf wp-content/cache/*`) AND
  `wp transient delete --all` after **any** DB import.
- Verify through HTTP / plain PHP, not wp-cli — wp-cli can still read the
  stale value from the object cache while php-fpm reads correctly.
  (Anchors playbook §9.4, risk register #25.)

## L7 — Import EXIT=0 but nothing happened — verify with a content probe
**(2026-08, 2026-08 first run — catch-up import)**

A catch-up import reported EXIT=0 but silently did nothing (transient
docker-exec pipe issue). If you cut over on that, you serve stale data.

Always verify the import's *effect*, not just its exit code:
```bash
mysql ... -e 'SELECT COUNT(*) FROM <prefix>options WHERE option_value LIKE "%<marker>%"'
# expect > 0 pre-replace / 0 post-replace — i.e. exactly what the import should have changed
```
(Anchors playbook §5.3, risk register #26.)

## L8 — Custom cert not served: nonexistent certresolver label
**(2026-08, 2026-08 first run — Traefik/Dokploy cutover prep)**

A compose router carried `tls.certresolver=cloudflare` but no resolver by
that name existed in Traefik's static config → Traefik logged "Router uses a
nonexistent certificate resolver" and served its default self-signed cert
instead of the uploaded custom cert. Fix: file-based TLS store in Traefik's
`dynamic/` dir (watched live), matching by SANs — no resolver needed.

Generalizable: if a custom cert upload "doesn't take effect", check the
router's `certresolver` label against the resolvers actually configured in
the proxy's static config, and prefer a dynamic TLS store for custom certs.
(Anchors playbook §6.2, §T10.)

## L9 — `www.` subdomain 404 after adding apex router
**(2026-08, 2026-08 first run — cutover prep)**

Adding the apex domain worked, but `www.` had no router → 404. Add the
www host as a first-class route/record (same cert — wildcard or SAN covers
both), and test both hosts before the flip. Also note: while the DB still
points at a staging URL, the site canonical-redirects the real domain to the
staging one (301) — expected pre-flip behavior, don't "fix" it.

## L10 — Streaming pipes: PowerShell 5.1 buffers binary output in RAM
**(2026-08, 2026-08 first run — multi-GB transfer)**

Piping native-command binary output through PowerShell 5.1
(`ssh A 'tar ...' | ssh B 'tar ...'`) buffers the stream as text lines in
RAM (observed 5+ GB and climbing). Use `cmd /c`, Git-Bash, WSL, or run the
whole pipe on one Linux host. Batch large transfers by logical unit.
(Anchors playbook §4.6.)

## L11 — Windows → remote script execution: CRLF and local interpolation
Run scripts with LF endings (`scp` then `bash /tmp/script.sh`), never piped
through `ssh ... bash -s` from PowerShell (CRLF breaks bash). PowerShell
interpolates `$()` in double-quoted ssh commands locally — use single
quotes or script files. (Anchors playbook §4.6, shared with
`coder-remote-servers` notes G11.)

## L12 — MySQL `--force` re-import is idempotent with `--add-drop-table`
Partial import failure (one bad table) → re-import with `mysql --force`,
then verify per-table row counts against source. `--add-drop-table` makes
the whole dump idempotent, so re-running is always safe. (Anchors playbook
§5.3.)
