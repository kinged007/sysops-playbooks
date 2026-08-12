# Playbook: WordPress Migration — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`.
Repo-level rules (folder discipline, secrets, committing): see `AGENTS.md`.

> **For agentic workers:** Execute this playbook linearly. Every phase has a
> checklist with `- [ ]` items. Do NOT skip Phase 0 (Discovery) — the entire
> downstream plan is parameterised by its answers. The playbook has **two
> mutually exclusive execution branches** chosen in Phase 1: **Branch A
> (Single-Run / Maintenance Page)** or **Branch B (Zero/Near-Zero Downtime /
> DNS Cutover)**. Never mix them.

**Goal:** Migrate a WordPress site from a source server to a destination
server with minimal risk, clear verification at every stage, and a defined
rollback path.

**Architecture:** Stateless approach — treat WordPress as *files + database +
configuration* and move each independently with verifiable checkpoints. Files
and DB are transferred to the destination **while the source stays live**
(staging), verified in isolation, then the switch is made via either a short
maintenance window (Branch A) or a DNS cutover with a final delta sync
(Branch B).

**Tech Stack:** `rsync`/`tar`/`scp`, `mysqldump`/`mysql`, `wp-cli`
(`wp search-replace`, `wp db export`), web server config (nginx/Apache), DNS
registrar tools, TLS/SSL, verification tools (`curl`, `wp core is-installed`,
`wp db check`).

---

## 0. Pre-flight (mandatory, every run)

- [ ] Read `notes/` — lessons from previous runs may change how you plan.
- [ ] Confirm prerequisites with operator (see README).
- [ ] Confirm with operator: source server is READ-ONLY for this run (backup +
      dumps excepted, each explicitly approved).
- [ ] Confirm with operator which **branch** applies (A or B) — see Phase 1.
- [ ] Record permission mode per AGENTS.md §1.3 (operator sets it at plan
      approval: A per-write confirm / B plan-as-approved).

## 1. Phase 0 — Discovery: questions to ask before anything

> Gather this information **from the site owner/operator** (and by inspecting
> the servers if credentials are provided). Record answers in the execution's
> `inventory.md` (Appendix B template). Questions are grouped; ask them in
> order. Mark whether each was *answered by operator* or *verified by
> inspection*.

### 1.1 The critical decision first (ask before anything else)

| # | Question | Why it matters |
|---|----------|----------------|
| D1 | **Will this be a single run-through (site shows a maintenance/upgrade page during migration), or must downtime be zero/near-zero (DNS cutover with live staging)?** | Selects **Branch A** vs **Branch B**. Everything downstream forks on this. |
| D2 | Is the destination a **brand-new empty site**, or does it already host content that must be preserved/merged? | Changes the whole import strategy (fresh import vs merge). Merging is out of scope here unless asked. |
| D3 | Does the **domain name stay the same** (server-to-server move) or **change** (old.com → new.com)? | Determines whether a serialization-safe search-replace of the DB is needed, and when. |
| D4 | What is the **acceptable downtime window** (minutes/hours/none), and is there a **preferred maintenance window** (day/time)? | Sets expectations, scheduling, and whether Branch B's more complex path is warranted. |
| D5 | Who is the **site owner / go-no-go approver**, and who should be notified? | Rollback decisions and cutover sign-off need a human authority. |

### 1.2 Source server — operator questions

| # | Question | Why it matters |
|---|----------|----------------|
| S1 | Hosting type: **VPS (you control OS), managed WordPress host (Kinsta/WP Engine etc.), cPanel/shared hosting**, or something else? | Determines access level and method. |
| S2 | **SSH access available?** (Preferred.) If yes, as what user? Root/sudo? | Access ladder (see 1.4). |
| S3 | Web server: **nginx, Apache (+ .htaccess?), LiteSpeed, OpenLiteSpeed**, IIS? | Config porting; `.htaccess` only works on Apache/LiteSpeed. |
| S4 | PHP version? PHP-FPM or mod_php? Any custom `php.ini` (memory_limit, upload_max_filesize, opcache)? | Destination must match or exceed; some plugins break on PHP version jumps. |
| S5 | MySQL/MariaDB version? | mysqldump compatibility, collation handling. |
| S6 | WP version? Is it **Multisite**? If multisite: number of subsites, subdomain vs subdirectory. | Multisite needs `--network` search-replace and `wp_blogs`/`wp_site` handling. |
| S7 | Active plugins & theme(s)? Any **custom/mu-plugins**? Any custom theme with hardcoded URLs? | Complicates search-replace; some plugins store absolute URLs in serialized options. |
| S8 | **Object cache** in use (Redis, Memcached, Varnish)? Config drop-in (`object-cache.php`)? | Must be ported/flushed; hardcoded cached URLs break after cutover. |
| S9 | **Cron**: WP-Cron or real system cron? Any `crontab` entries that touch WP? | Real cron must be recreated on destination. |
| S10 | **CDN** in front (Cloudflare, etc.)? Caching/TTL settings? | Affects DNS cutover and cache purging. |
| S11 | **Email**: is mail sent from this server (SMTP, PHP mail, transactional plugin)? Any domain MX/SPF/DKIM tied to the server? | Server-to-server mail server migration may be needed; DNS changes can break DKIM/SPF. |
| S12 | **SSL**: Let's Encrypt/custom cert? Wildcard? Terminated at server or at CDN? | Certificate must be issued/ported for destination. |
| S13 | Approximate **site size**: files (esp. `wp-content/uploads`) and DB size? | Transfer strategy & timeout planning. |
| S14 | Any **.htaccess custom rules** (redirects, security headers, caching) or web-server-level rewrites? | Must be recreated on destination or traffic breaks. |
| S15 | Any scheduled jobs outside WP (backup scripts, import scripts, webhooks writing to the site)? | Data written between snapshot and cutover = the "delta" problem. |

### 1.3 Destination server — operator questions

| # | Question | Why it matters |
|---|----------|----------------|
| T1 | Hosting type / provider (VPS, managed host, cPanel)? | Method & tooling. |
| T2 | **SSH available?** Root/sudo? | Access ladder. |
| T3 | Web server & PHP version installed or installable? | **Must match source exactly (like-for-like), never upgrade** (S3/S4). |
| T4 | MySQL/MariaDB version installed or installable? | **Must match source exactly (like-for-like), never upgrade** (S5). |
| T5 | Is WP already installed here, or is it a bare server? | Fresh import vs overlay. |
| T6 | Disk space available? (Must exceed source total × ~1.5 for dump + extracted site.) | Out-of-disk is a top-5 migration killer. |
| T7 | Firewall/security groups: are SSH, HTTP/S open? Can destination reach source (or vice versa) for transfer? | rsync port (22) needs reachability *in the right direction*. |
| T8 | Can a **temporary staging hostname/subdomain** (e.g. `staging.<DOMAIN>`) point at the destination, or must preview use `/etc/hosts` only? | Determines preview method (see Phase 6). |
| T9 | Object cache available at destination (Redis etc.)? | Match source config. |
| T10 | SSL issuance method at destination (Let's Encrypt, panel-provided, wildcard)? | Needed before HTTPS preview works. |
| T11 | Database service details: how to create DB/user/grants (root SSH, panel, or credentials provided)? | Needed for Phase 4. |
| T12 | Existing cron/user/system accounts to reuse or create? | Ports S9. |

### 1.4 Access ladder (agent must assess both servers)

> **Preference order.** Use the highest level available on *each* server
> independently; the method selected in Phase 1 must be compatible with the
> *weakest* link.

| Level | Capability | Typical server types | What you can do |
|-------|-----------|---------------------|-----------------|
| **L4** | SSH + root/sudo | VPS, dedicated, cPanel w/ root | Everything: rsync, mysqldump, WP-CLI, install tools, edit configs. |
| **L3** | SSH (non-root) | Managed VPS, some hosts | Most things; DB dumps via `wp db export` (uses wp-config creds), rsync to writable dirs, WP-CLI if installed. May lack permission to edit `/etc/*` or service configs. |
| **L2** | No SSH; SFTP/FTP + hosting panel (phpMyAdmin, file manager) | cPanel/shared, some managed hosts | Upload files via SFTP; DB via phpMyAdmin import; preview via staging subdomain in panel. |
| **L1** | WP admin only | locked-down managed hosts | Use a migration **plugin** (Duplicator, All-in-One WP Migration, UpdraftPlus) for packaging, download the archive, import via the plugin on the destination. |

**Source-availability matrix** (read "source has…"):

| Source \ Dest | L4 SSH | L3 SSH | L2 panel | L1 admin |
|---------------|--------|--------|----------|----------|
| **L4 SSH** | rsync + mysqldump, push or pull | rsync push → dest via SCP/SFTP; import via dest WP-CLI if available | rsync/SCP push to panel-accessible dir; DB import via phpMyAdmin | package via WP-CLI; download archive; import via plugin |
| **L3 SSH** | dest pulls from source via rsync/scp; or source pushes | push/pull both fine | SCP out to panel dir; phpMyAdmin import | package via WP-CLI |
| **L2 panel** | panel export (cPanel backup / phpMyAdmin export) → pull via SFTP/SCP | same, dest pulls | cPanel backup restore / phpMyAdmin | plugin export |
| **L1 admin** | plugin export → pull archive | same | same | plugin-to-plugin archive |

**Rule:** If you have SSH on the source, **use `wp db export` / `mysqldump`
and `rsync`** — it's the most reliable. Plugins are the fallback for L1.

### 1.5 DNS & domain questions

| # | Question | Why it matters |
|---|----------|----------------|
| N1 | Where is DNS hosted (registrar, Cloudflare, another DNS provider)? | Where the cutover happens. |
| N2 | Are there **A/CNAME/AAAA records** for the domain and any subdomains (`www`, `staging`, mail subdomains)? | Which records to change. |
| N3 | Current **TTL** on the record(s)? | TTL must be lowered *in advance* for fast cutover (Branch B). |
| N4 | Is the site behind **CDN proxy (orange cloud)** or is the IP directly served? | Proxied = TTL largely irrelevant + need cache purge; direct = TTL matters. |
| N5 | **Mail**: does the domain have MX records pointing to the source server's mail? Any SPF/DKIM/DMARC referencing the source IP/hostname? | Moving the web app must not silently break email; mail often should NOT move with the web migration. |

---

## 2. Phase 1 — Decide method, branch, and rollback plan

### 2.1 Choose the transfer method (based on access ladder, §1.4)

| Method | When | Pros | Cons |
|--------|------|------|------|
| **M1: rsync + mysqldump (SSH)** | Source & dest at L3+ | Fast for large sites, resumable, delta-capable (Branch B), full control | Needs SSH; needs matching path/permission care |
| **M2: tar/zip + SCP/SFTP** | L2/L3, single push | Simple, no rsync needed | Not resumable mid-file; no cheap delta for Branch B |
| **M3: Migration plugin (Duplicator / All-in-One WP Migration / UpdraftPlus)** | L1, or any | Works with admin-only access; bundles files+DB; handles search-replace | Adds plugin dependency; large sites hit upload limits; archive extraction needs memory/time; less auditable |
| **M4: Hosting-provider import tool (managed hosts)** | Managed dest | Provider-specific, easy | Vendor lock; limited control |

**Default recommendation:** **M1** whenever SSH is available (it almost always
is on the source). Use **M3** only when the access ladder forces it.

### 2.2 Choose the branch

- **Branch A (Single-Run / Maintenance Page):** Put the site behind a
  maintenance/upgrade page, do the migration, verify, take the page down.
  Downtime = the migration duration (minutes to hours). Simplest, most
  predictable.
- **Branch B (Zero/Near-Zero Downtime):** Stage and fully verify the site on
  the destination while the source serves traffic. Then:
  1. Lower DNS TTL in advance.
  2. Do a **final delta sync** of files + a **fresh DB dump** at cutover time.
  3. Flip DNS.
  4. After DNS propagates, **optionally re-sync the DB once more** to catch
     any writes that landed on the source during propagation, then freeze the
     source.

  User-visible downtime ≈ seconds-to-minutes. **Requires** SSH on source (or
  at least DB-level dump access) for the delta sync, and control of DNS TTL.

> **Recommendation to operator:** If the site can tolerate even a short
> maintenance window and there's no strict uptime requirement, **Branch A is
> dramatically simpler and safer**. Use Branch B only when real uptime
> requirements exist. (The "upgrade page" itself is a small artifact — a
> static `maintenance.html` served by the web server with a 503 — see §8.2.)

### 2.3 Define the rollback plan (before any work starts)

> **A rollback plan is not optional.** At minimum: a verified full backup of
> source stored **off the source server**, and a documented revert path.
> Choose one:

| Rollback strategy | What it protects | Revert action |
|-------------------|------------------|---------------|
| **R1: Full backup revert** (always mandatory) | Total loss/corruption on source | Restore files+DB from off-box backup; source web server untouched until cutover, so "revert" = simply don't cut over. |
| **R2: DNS flip-back (Branch B only)** | Broken new site after cutover | Point DNS back to old source IP; source still fully live because it was never stopped. Then re-plan. |
| **R3: DB snapshot restore on dest** | Bad search-replace / import on destination | Re-import the pre-transform DB dump (or restore dest DB from snapshot) and re-run only the safe steps. |
| **R4: File-level revert on dest** | Wrong file state | Re-copy from a pristine staging copy (keep one untouched copy of files + dump before applying search-replace). |

**Rollback trigger rules (any one → STOP and revert):**
- Any destructive step that wasn't preceded by a completed backup.
- Destination fails a required verification in Phase 6 that can't be fixed
  within the rollback budget (time/effort).
- Branch B: after DNS flip, >5% of core checks fail within the first 15
  minutes (unless fixable in < the acceptable downtime budget).
- Data corruption detected (e.g. `wp db check` reports errors,
  serialized-data corruption, missing tables).

### 2.4 Validate the destination stack with a test page (before committing to the plan)

> **Why:** the method/branch/rollback decisions (§2.1–2.3) are only sound once
> you know the destination can actually serve **HTTP → PHP → DB**. Do a
> throwaway test-page bring-up of the destination stack *before* investing in
> transfer work. This catches infra problems (web server config, container
> networking, TLS, reverse proxy) in minutes instead of mid-migration.
> (Verified 2026-08: an empty destination web root returning `403` was a
> *normal* state — the test page is how you prove the stack, not the absence
> of files.)

- [ ] Provision the destination web stack (containers/services up, volumes present).
- [ ] Drop a minimal `test-index.php` into the destination web root:
  ```php
  <?php
  header('Content-Type: text/plain');
  echo 'PHP ', phpversion(), "\n";
  foreach (array('imagick','redis','memcached','intl','gd','mbstring') as $e) {
      echo str_pad($e, 12), extension_loaded($e) ? "OK\n" : "MISSING\n";
  }
  $t = @fsockopen('db', 3306, $errno, $errstr, 3);   // use the DB service name
  echo 'DB reachable: ', $t ? "yes\n" : "no ($errstr)\n";
  if ($t) { fclose($t); }
  echo 'REQUEST_URI: ', $_SERVER['REQUEST_URI'], "\n";
  echo 'HTTPS: ', isset($_SERVER['HTTPS']) ? $_SERVER['HTTPS'] : 'off', "\n";
  ```
  (Adjust the extension list to the site's needs and `db` to the real DB
  service name.)
- [ ] Load it via the public URL **and** via the origin directly. **Pass
      criteria:**
  - HTTP `200`; PHP version matches the source (like-for-like, §intro)
  - required PHP extensions present
  - DB service reachable from the PHP runtime (proves container networking)
  - HTTPS / `X-Forwarded-Proto` correctly detected behind the proxy (proves
    cookies/TLS will behave)
- [ ] Fix any infra failure NOW and re-test. Do not start transfer work on a
      broken stack.
- [ ] The test page is superseded by the real `index.php` during Phase 3 — or
      remove it explicitly.

---

## 3. Phase 2 — Pre-migration preparation (source & destination)

### 3.1 Source preparation

- [ ] **Q1-1.4:** Confirm access level and document it in the inventory.
- [ ] **WRITE** — **Take a full backup** of files and DB, store **off the
      source server** (local machine / object storage / another box).
      - Files: `rsync -a` or `tar czf` of the full WP root.
      - DB: `wp db export` or `mysqldump` (see Appendix A, §A.2).
      - Rollback: backup is additive; source is untouched otherwise.
- [ ] **Verify the backup**:
      - Files: `tar tzf backup.tar.gz | wc -l` shows plausible count; or
        rsync `--dry-run` shows zero differences on a test re-run.
      - DB: `mysql -e "SOURCE backup.sql; SHOW TABLES;"` against a throwaway
        DB, or at least `gzip -t`.
- [ ] **Record the Site Health Snapshot** (Appendix B) in the execution's
      `inventory.md`: WP version, PHP, MySQL, active plugins, uploads size,
      DB size, cron entries, `.htaccess` contents, `wp-config.php` DB
      creds/salts (do not record secrets — reference them), object-cache
      drop-in presence, list of DB tables.
- [ ] **Record the DB dump timestamp as the migration checkpoint** — it's
      embedded in the dump (`-- Dump completed on YYYY-MM-DD hh:mm:ss`) and in
      the inventory. Everything written on the source *after* it must be
      reconciled at cutover. A small diff later enables a **surgical delta**
      (compare high-write tables: `wp_posts`, `wp_postmeta`, `wp_options`,
      `wp_comments`, order/order-item tables) instead of a full
      re-migration.
- [ ] **Identify write sources** (new comments, form submissions, orders,
      cron output) — these are the "delta" for Branch B and the reason for
      maintenance mode in Branch A.
- [ ] If Branch B: **note current DNS TTL** (N3) and if TTL > 300s, schedule
      TTL lowering **24–48h before cutover** (§9.1).
- [ ] **Do NOT** change anything else on the source yet. Source stays
      authoritative until cutover.

### 3.2 Destination preparation

- [ ] **WRITE** — **Confirm/install matching software versions (from
      S4/S5/T3/T4) — CRITICAL: match like-for-like.** PHP and MariaDB/MySQL
      versions must **match the source exactly** (same major.minor, pin patch
      where possible). Do **NOT** upgrade either as part of the migration.
      Pin exact container image tags in the compose file (e.g.
      `php:<VER>-fpm`, `mariadb:<VER>`). Record the exact source/dest
      versions in the inventory. Collation support must match (`utf8mb4`).
      Rollback: image pins live in the compose file; revert = checkout
      previous compose.
- [ ] **WRITE** — Create the **web root directory**; ensure disk space (T6)
      is free.
- [ ] **WRITE** — Create the **database + user + grants** (T11). Record
      DB name/user/pass/host for wp-config. Grant: `SELECT, INSERT, UPDATE,
      DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES, LOCK TABLES, CREATE
      TEMPORARY TABLES` on the new DB. Rollback: drop the test DB (no live
      data yet).
- [ ] **WRITE** — Set up **web server virtual host** for the destination
      (site root, PHP handler, SSL). For now it can serve a placeholder or be
      closed; final config in Phase 5. Rollback: revert vhost file / disable
      site.
- [ ] **WRITE** — If object cache will be used: install Redis/Memcached +
      PHP extension now (T9).
- [ ] **WRITE** — Create/configure the **cron user** and plan the ported
      cron jobs (S9) for after cutover.
- [ ] **WRITE** — Set up the **staging hostname** for preview (T8): create
      DNS record `staging.<DOMAIN>` → destination IP, or confirm
      `/etc/hosts` preview is acceptable (preferred for "same domain, HTTPS,
      no cert for staging" simplicity — but note mixed-content/cookies
      caveats in §6.3).
- [ ] If Branch B: confirm the destination can be reached from the source on
      the transfer port (or source from destination) and that the **delta
      sync path is pre-tested** (§9.2) before the day.

---

## 4. Phase 3 — Transfer files

> Transfer happens **while the source is live**. Do not take the source down
> yet. Both branches do this identically.

### 4.1 What to transfer

The WordPress file tree contains, at minimum: `index.php`, `wp-admin/`,
`wp-includes/`, `wp-content/`, `wp-config.php`, `.htaccess`, and any custom
drop-ins. **Transfer the entire web root** for a faithful copy, then fix
config in Phase 5.

Consider excluding (decide per site):
- `wp-content/cache/` and object-cache working dirs — regenerate.
- `*.log`, `wp-content/debug.log` — regenerate.
- `wp-content/advanced-cache.php`, `object-cache.php` — copy them, but
  flush/verify cache at destination (§4.5).
- `.git/` if present in the tree.
- **`wp-config.php` — exclude when the destination needs a custom config**
  (e.g. different DB_HOST/passwords) or a later `--delete` re-sync will
  clobber the destination's working config (verified incident 2026-08).
  Decide per run and record the decision in the inventory.

### 4.2 Method M1 — rsync (L3+/L3+)

```bash
# From a jump host or the source (push) — or reverse the direction for pull.
rsync -avz --partial --progress \
  <SOURCE_WP_ROOT>/  <DEST_SSH>:<DEST_STAGING_PATH>/
```

For a large `uploads/` this is resumable and delta-friendly. Repeat until
`rsync --dry-run` reports no differences (idempotent — safe to run
repeatedly).

### 4.3 Method M2 — tar + SCP/SFTP (L2/L3)

```bash
cd /var/www && tar czf site.tar.gz site/
scp site.tar.gz <DEST_SSH>:/tmp/
# On dest:
cd /var/www && tar xzf /tmp/site.tar.gz
```

Large archives risk timeouts; prefer rsync when possible.

### 4.4 Method M3 — migration plugin

1. On source: install **Duplicator** (or All-in-One WP Migration /
   UpdraftPlus), run a package/backup **that includes the DB**, download the
   archive + installer.
2. Transfer the archive to the destination (SFTP or web upload).
3. On dest: run the installer (Duplicator) / import (AIO / UpdraftPlus). The
   plugin handles DB import + search-replace. **Verify the plugin's
   search-replace actually ran** — spot-check that `wp_options`
   `siteurl`/`home` are correct (Appendix A, §A.4).
4. **WRITE** — Delete the installer files after successful install
   (security). Rollback: none needed — installer is dead code.

### 4.5 After transfer — file-level checks

- [ ] Verify file count/size parity: `rsync -av --dry-run` empty on re-run
      (M1), or `du -sh` compares.
- [ ] **WRITE** — **Permissions & ownership** (classic failure): on the dest,
  ```bash
  chown -R www-data:www-data <DEST_WP_ROOT>/        # or your dest web user
  find <DEST_WP_ROOT> -type d -exec chmod 755 {} \;
  find <DEST_WP_ROOT> -type f -exec chmod 644 {} \;
  chmod 755 <DEST_WP_ROOT>/wp-content/uploads        # writable uploads, etc.
  ```
  (Adjust to match the destination's web-server user — commonly `www-data`,
  `nginx`, `apache`, or `bitnami`.)
  > **⚠️ `chmod 750` on `uploads` breaks nginx static serving when nginx and
  > PHP run as different users** (verified 2026-08: Docker nginx→php-fpm,
  > nginx user ≠ `www-data`). `750` denies "others" (`o+rx`) so nginx gets
  > `13: Permission denied` / HTTP 403 on every upload. In a split-user
  > setup, make `uploads` **`755`** — PHP keeps write access via *ownership*
  > (it owns the files), nginx gets traverse+read as "others". Only use
  > `750` when the web server and PHP share the same group.
- [ ] **WRITE** — Flush any copied object-cache keys (see §9.4 flush step)
      so stale cached URLs don't poison the preview.
- [ ] Copy `.htaccess` (Apache/LiteSpeed) only if the dest web server
      supports it — nginx needs its equivalent `try_files` rules (Appendix
      A, §A.7).

### 4.6 Transfer efficiency & memory (practical notes — verified 2026-08)

- **Run streaming pipes natively, not through an object-oriented shell.** On
  Windows PowerShell 5.1, piping one native command's binary output into
  another (`ssh A 'tar ...' | ssh B 'tar ...'`) buffers the stream in memory
  as text lines — a multi-GB transfer balloons RAM (observed 5+ GB and
  climbing). Use `cmd /c` or a real shell (Git-Bash / WSL / a Linux jump
  box) for the pipe so the OS pipe buffers at ~64 KB. Prefer running the
  whole pipe **on one Linux host** (both endpoints reachable) to avoid the
  orchestrator relaying gigabytes at all.
- **Batch large transfers by logical unit** (core tree,
  `wp-content/plugins`, `wp-content/themes`, `wp-content/uploads/<year>`,
  plugin-owned upload dirs) for resumability and per-batch checkpoints. A
  single multi-GB stream is fragile and hard to resume.
- **`tar` over SSH is a solid fallback when rsync isn't on the orchestrator**
  (rsync is not bundled with Windows OpenSSH):
  `ssh <SOURCE_SSH> 'cd <SOURCE_WP_ROOT_DIR> && tar czf - --exclude=... site/' | ssh <DEST_SSH> 'tar xzf - -C <DEST_PARENT>'`.
  Read-only on the source (nothing written there), compresses on the wire.
  Caveat: not resumable mid-stream, and `file changed as we read it`
  warnings are normal on live trees (harmless for a backup; the
  authoritative copy happens at cutover).
- **Compression ROI depends on content.** Text logs compress ~10× (worth
  it); already-compressed binaries (PDF/JPEG) barely compress. Take a
  `du -sh` breakdown of subdirs *before* batching so you split where the
  bytes actually are.
- **Transfer nothing regenerable or redundant**: caches, `*.log`, backup
  zips/artifacts, updraft/Dropbox backups, temp dirs. Verify parity after
  with file counts (`find | wc -l`) and `du -sh` per top dir. Beware: `du`
  on a huge cache tree can time out — exclude it before measuring.
- **Record a migration checkpoint timestamp** the moment the DB dump is
  taken (it's embedded in the dump: `-- Dump completed on ...`). This is
  the delta baseline for a surgical catch-up at cutover instead of a full
  re-migration (§3.1).

---

## 5. Phase 4 — Transfer & transform the database

### 5.1 Dump the source DB (L3+ or panel)

**WRITE** — these dump commands write a file on the source and read the
production DB (SELECT/export only). One operator approval covers the dump
run; each dump is additive to `/tmp` and cleaned up after transfer.

**Preferred (WP-CLI, uses wp-config creds):**
```bash
cd <SOURCE_WP_ROOT> && wp db export /tmp/site-$(date +%F).sql --add-drop-table --single-transaction --quick
```
(`--single-transaction` = consistent InnoDB snapshot without locking;
`--add-drop-table` makes re-import idempotent.)

**Alternative (raw mysqldump):**
```bash
mysqldump --single-transaction --quick --add-drop-table \
  -h <DB_HOST> -u <DB_USER> -p <DB_NAME> > /tmp/site-$(date +%F).sql
```

**Panel (L2/L1):** use phpMyAdmin export (SQL, "Add DROP TABLE",
"compressed if large") or the host's backup tool.

- [ ] Compress the dump for transfer: `gzip /tmp/site-*.sql` (usually 5–10×
      smaller).
- [ ] Verify the dump is not empty and not truncated: `gzip -t file.sql.gz
      && gzip -dc file.sql.gz | wc -l` (line count > 0 and large).
- [ ] **Binary/blob columns need `--hex-blob`.** If the site has binary
      columns (e.g. Wordfence's `binary(16)` IP columns), a plain text dump
      round-trips some rows badly and the import fails with `Duplicate
      entry ... for key 'PRIMARY'` on otherwise-clean data. Re-dump just
      those tables with `mysqldump --hex-blob --add-drop-table ... DB tbl1
      tbl2` and re-import (hex literals survive the round-trip exactly).
      Verified 2026-08: `wfblockediplog`, `wfblocks7`.
- [ ] **⚠️ Always pass `--default-character-set` to mysqldump when the server
      default differs from the table charset.** On a source where
      `character_set_server=latin1` but the WP tables are `utf8`, mysqldump
      without an explicit charset follows the latin1 default and
      **silently corrupts UTF-8 multibyte sequences in the dump file** —
      e.g. non-breaking space `\xC2\xA0` becomes `??` (`0x3F 0x3F`). The
      source renders fine; the corruption only surfaces on the destination
      as `??` sprinkled through content. Verified 2026-08: the dump itself
      contained `3F 3F` where the DB had `C2 A0`. **Fix:** dump with
      `--default-character-set=utf8` (matching the tables — `utf8mb4` and
      `binary` also round-trip cleanly) and **verify the dump round-trips**
      by hex-comparing a known multibyte sample against the source before
      importing. Combine with `--hex-blob` for binary columns in one pass.

### 5.2 Transfer the dump

Same channel as files (rsync / scp / SFTP / plugin). For very large DBs,
prefer transferring the `.sql.gz` and importing from the compressed stream
(§5.3).

### 5.3 Import into destination DB

**WRITE** — this replaces the destination DB contents. Confirmation required
per AGENTS.md database rule.

```bash
# On dest, from the site dir (needs DB creds in wp-config, or specify):
gzip -dc /tmp/site.sql.gz | mysql -h <DEST_DB_HOST> -u <DEST_DB_USER> -p <DEST_DB_NAME>
# or via WP-CLI once wp-config points at the new DB:
wp db import /tmp/site.sql
```

- [ ] On success, verify: `wp db check` and `wp db size`, or
      `mysql ... -e "SHOW TABLES;"` shows the expected table set.
- [ ] If a full import hits an **isolated** error (one table), re-import
      with `mysql --force` to finish everything else, then **verify
      per-table row counts against the source** (`SELECT COUNT(*)` on the
      key tables; optionally a full table-count pass). `--force` skips only
      the offending statement. `--add-drop-table` makes the whole dump
      idempotent, so re-running it is always safe.
- [ ] **Charset/collation:** ensure the new DB/table collation matches the
      source (dumps carry `DEFAULT CHARSET` in CREATE TABLE, but the
      DB-level default matters for new tables). Check with
      `SHOW VARIABLES LIKE 'character_set_database';` and
      `SHOW VARIABLES LIKE 'collation_database';`. UTF-8/`utf8mb4` is the
      WP standard.

### 5.4 Serialization-safe URL search-replace

> **Never use raw `sed` on a WP database.** Serialized PHP strings (in
> `wp_options`, `wp_postmeta`, widget settings, some plugin settings) store
> **string lengths**; changing the URL length without updating those lengths
> corrupts the data. WP-CLI and Better Search Replace handle this. Skipping
> `guid` is required (it's used for feeds/imports, changing it is harmless
> but can confuse downstream readers).

**When is search-replace needed?**
- **Domain changes** (D3 = new domain): always.
- **Same domain, staging preview via a temporary hostname:** replace real
  domain → staging hostname for the preview, then staging → real domain at
  cutover. (Or avoid by using `/etc/hosts` preview where the site keeps its
  real domain — no replace needed — see §5.5.)
- **Same domain, direct preview (no hostname change):** no replace needed.
- **⚠️ Filesystem path changes (verified gotcha, 2026-08):** even with an
  **unchanged domain**, the DB often contains the **source server's
  absolute filesystem paths** — e.g. EWWW Image Optimizer `aux_paths`,
  Freemius `fs_active_plugins`/`fs_accounts` (`abspath`), SiteOrigin widget
  paths, `recently_edited`, PDF-invoice template paths, analytics proxy
  cache dirs. If the destination mounts the site at a different path (any
  container path vs. the old host's `/var/www/vhosts/...`), these break
  silently. Detect on the source during Phase 0:
  ```sql
  SELECT option_name, LEFT(option_value,120) FROM <TABLE_PREFIX>options
   WHERE option_value LIKE '%/var/www/%' OR option_value LIKE '%/home/%'
  ```
  Then fix serialization-safely on the destination (never raw
  `sed`/`UPDATE`):
  ```bash
  wp search-replace '<SOURCE_WP_ROOT>' '<DEST_WP_ROOT>' \
    --all-tables-with-prefix --precise --recurse-objects --skip-columns=guid
  ```
  Choose the destination path **deliberately** so this is a single clean
  replace. Re-run the dry-run pattern after to confirm zero matches remain.

**Post-replace verification — the "leftover scan"** (run after any
search-replace):
```sql
SELECT option_name, LEFT(option_value,90) FROM <TABLE_PREFIX>options
 WHERE option_value LIKE '%<old>%'
   AND option_value NOT LIKE '%<new>%'
   AND option_value NOT LIKE '%@<old>%';   -- emails are intentional; keep them
```
Also scan `postmeta.meta_value` and `posts.post_content` the same way. Then
load the front page and check the **rendered HTML** (not just the DB) — a
stale page cache can serve pre-replace HTML (§ below).

**Known limitations of `wp search-replace --precise --recurse-objects`
(verified 2026-08):**
- Serialized objects of **unloaded classes** (MailChimp, WPML, WCML,
  Freemius, …) are silently skipped (only a `Skipping an uninitialized class
  "…"` warning) — old strings stay inside plugin cache/settings. These are
  typically not front-end content and are correct again once the domain is
  reverted at cutover. To fix at staging time, load the plugin's classes
  first (e.g. run the replace with that plugin active).
- The **`guid` column is correctly left alone** by `--skip-columns=guid` —
  GUIDs are permanent identifiers and must not change. A dry-run total that
  includes guid will look alarming (tens of thousands); ignore it.
- **Double-escaped URLs** (JSON / `\u005c`-escaped slashes, e.g. from a
  page-builder import) evade both the URL replaces and `wp search-replace`.
  Fix per-row with a bare `REPLACE(col, '<old>', '<new>')` limited to rows
  that match `LIKE '%<old>%'` but not `LIKE '%<new>%'` nor
  `LIKE '%@<old>%'`. **Plain-text columns only** — never run a bare
  `REPLACE` on serialized columns (`postmeta.meta_value`,
  `options.option_value`).
- **Purge page caches after replacing.** A file page cache (W3TC
  `page_enhanced`, served via the `advanced-cache.php` drop-in) holds
  pre-replace HTML and serves it as stale content. `wp cache flush` only
  clears the object cache; delete `wp-content/cache/*` (regenerates) and
  purge any CDN.

**WRITE** — Do it after import, on the destination, using WP-CLI:
```bash
cd <DEST_WP_ROOT>
wp search-replace '<OLD>' '<NEW>' \
  --all-tables-with-prefix --precise --recurse-objects --skip-columns=guid --dry-run
# inspect output, then re-run WITHOUT --dry-run
wp search-replace '<OLD>' '<NEW>' \
  --all-tables-with-prefix --precise --recurse-objects --skip-columns=guid
```
Rollback: R3 (re-import the pre-transform dump). Notes:
- Run `http://` and `https://` variants, and the bare domain, to catch mixed
  forms. (WP-CLI replaces the string wherever it appears; the URL protocol
  may need two passes.)
- Multisite: add `--network`.
- Use `--precise` for serialized-data safety (slower but thorough); on
  large DBs you can accept the default unless you hit weirdness.
- After replace, **flush transient caches** in the DB (they cache old
  URLs): `wp transient delete --all`.
- **Never** change the `siteurl`/`home` options by hand in SQL if you can
  avoid it; `wp option update home https://<NEW>` and
  `wp option update siteurl https://<NEW>` is the clean way (Appendix A,
  §A.4).

### 5.5 Preview strategy decision (also see Phase 6)

| Scenario | Search-replace for preview? | Preview method |
|----------|------------------------------|----------------|
| Same domain + `/etc/hosts` preview on your testing machine | **No** (DB keeps real domain) | `/etc/hosts` line `<DEST_IP> <DOMAIN> www.<DOMAIN>`, browse normally (cookies/HTTPS caveats, §5.6) |
| Same domain + public `staging.<DOMAIN>` | Yes: real → `staging.<DOMAIN>` | Access `https://staging.<DOMAIN>` |
| New domain | Yes: old → new | Access `https://<NEW>` directly (point it at dest before DNS swap, or use hosts) |

### 5.6 HTTPS & cookies during preview

- Preview over HTTPS requires a valid cert for the hostname you're using.
  Options: (a) issue a real cert for `staging.<DOMAIN>` / the new domain now
  (Let's Encrypt supports this), or (b) if previewing the real domain via
  `/etc/hosts`, keep the source's cert validity — but the destination must
  have a cert for that domain too, else you get a browser warning.
- **Cookie/domain caveat:** WP cookies are scoped to the domain. Previewing
  the real domain via `/etc/hosts` from your machine while the rest of the
  world hits the source is fine — you just need to log in separately on
  each. No conflict.
- **Mixed content:** if the DB contains `http://` absolute asset URLs and
  you preview over HTTPS, they'll be blocked; the search-replace (or the
  final cutover to a https site) resolves this.

---

## 6. Phase 5 — Configure wp-config.php & web server

### 6.1 wp-config.php on the destination

- [ ] **WRITE** — Edit `wp-config.php` (or use a fresh WP's sample config)
      to point at the **destination** DB:
  ```php
  define( 'DB_NAME', '<DEST_DB_NAME>' );
  define( 'DB_USER', '<DEST_DB_USER>' );
  define( 'DB_PASSWORD', '<DEST_DB_PASS>' );   // from this run's secrets/, never inline
  define( 'DB_HOST', '<DEST_DB_HOST>' );   // or DB socket/host per destination
  ```
  Rollback: keep a copy of the transferred config; revert = restore it.
- [ ] Verify `$table_prefix` matches the imported DB's prefix (from the
      inventory).
- [ ] **WRITE** — **Regenerate salts** (forces all existing sessions/cookies
      to be invalid, so everyone must re-login — acceptable at cutover; it
      also avoids shipping the source's keys around):
  ```bash
  wp config shuffle-salts     # if WP-CLI; or paste fresh keys from https://api.wordpress.org/secret-key/1.1/salt/
  ```
- [ ] **`wp config set --raw` writes raw PHP — for literals only** (`true`,
      `false`, `0`). Passing a string with `--raw` produces
      `define('DB_HOST', db);` — unquoted, so PHP raises "undefined
      constant" warnings and it only works via PHP 7.x's legacy string
      fallback. **Omit `--raw` for string values.**
- [ ] wp-cli refuses to run as root without `--allow-root` — add it on
      servers/containers where you exec as root.
- [ ] Match/enable performance constants that existed on source: `WP_CACHE`,
      `WP_DEBUG`, `WP_ENVIRONMENT_TYPE`, `DISABLE_WP_CRON`,
      `WP_MEMORY_LIMIT`, object-cache settings. Do **not** copy source paths
      that don't apply (e.g. `WP_HOME`/`WP_SITEURL` hard-coded to the old
      domain — set them only if needed for the staging hostname).
- [ ] If you copied `wp-content/object-cache.php` / `advanced-cache.php`,
      ensure the cache backend config (redis host/port) is updated for the
      destination and the cache is flushed (§9.4).

### 6.2 Web server virtual host

- [ ] **WRITE** — Point the vhost at the transferred web root. Rollback:
      restore previous vhost file.
- [ ] **WRITE** — Port PHP handler config (PHP-FPM pool, `memory_limit`,
      `upload_max_filesize` ≥ source values).
- [ ] **WRITE** — Port **rewrites**:
      - Apache: `.htaccess` (already copied) must be allowed
        (`AllowOverride All`).
      - nginx: add the standard WP `try_files $uri $uri/ /index.php?$args;`
        and PHP-FPM `location ~ \.php` block (Appendix A, §A.7).
- [ ] **WRITE** — Port any custom redirects/security headers/caching rules
      from source (S14).
- [ ] **WRITE** — Add the **staging hostname** to the vhost's `server_name`
      (for preview) — remember to remove it at cutover, or make the cutover
      just a config change, not a vhost change.
- [ ] **Block public access to the staging site** unless you want it
      browsable (optional; it's usually fine to leave it reachable on
      `staging.` since it's not indexed). If sensitive, add basic-auth or
      firewall rule on the dest for the preview phase.
- [ ] **WRITE** — Issue/configure TLS (§T10) for the preview hostname.

---

## 7. Phase 6 — Staging, preview & testing on destination

> **The destination is now a full, live-looking clone of the site, reachable
> via its staging hostname or `/etc/hosts`, while the source continues
> serving production.** This is the verification gate. **Do not proceed to
> cutover until the whole checklist below passes.**

### 7.1 Bring it up

- [ ] **WRITE** — Confirm DB import done (§5.3), files in place (§4.5),
      wp-config set (§6.1), vhost reloaded (`nginx -t && systemctl reload
      nginx`, or `apachectl -t && apachectl graceful`). Rollback: previous
      config + reload restores.
- [ ] Check PHP-FPM/php handler is healthy: `php -v`, and request a page.
- [ ] Open the site at the preview hostname (or via `/etc/hosts`). Expect a
      loadable front page. **If you get 500: check `wp-content/debug.log` /
      PHP error log immediately** (top cause: missing PHP extension, wrong
      file perms, DB creds, or search-replace corrupted data).

### 7.2 Automated smoke checks (run these commands; record all output)

```bash
# HTTP layer
curl -sS -o /dev/null -w "%{http_code}\n" https://<PREVIEW_HOST>/           # expect 200
curl -sS https://<PREVIEW_HOST>/ | head -c 200                              # sanity: HTML, not error text

# WP layer (from the site dir)
wp core is-installed                                                      # Success
wp core version                                                            # matches source
wp db check                                                                # OK
wp option get home && wp option get siteurl                               # correct domain
wp plugin list --status=active --field=name                               # matches source active set
wp theme list --status=active --field=name

# Inspect the logs for errors after loading the page
tail -n 50 wp-content/debug.log 2>/dev/null; tail -n 50 /var/log/php*.log
```

### 7.3 Manual / browser verification checklist (go/no-go gates)

> Mark each PASS/FAIL. Any FAIL blocks cutover until fixed and re-checked.

- [ ] Front page loads (200), shows correct content, no fatal errors.
- [ ] Internal links navigate correctly (click-through of home, a post, a
      page, an archive, a search result).
- [ ] **All images/static assets load** (uploads, theme assets) — no broken
      images (top candidate: search-replace didn't cover
      `wp-content/uploads` URL references, or file perms).
- [ ] `wp-admin` login works (you'll need to log in fresh due to new salts).
- [ ] A few **core features** work: comments/forms (if present), any key
      plugin (eCommerce cart/page, members, LMS, etc.).
- [ ] **Permalinks** work (pretty URLs, not just `?p=`).
- [ ] SSL cert valid, no warnings on the preview hostname.
- [ ] **Object cache** working (if used): cache plugin reports connected;
      `redis-cli ping` → PONG.
- [ ] **Cron** (WP-Cron): `wp cron event list` shows scheduled jobs; run
      one: `wp cron event run --all`.
- [ ] Search-replace spot checks: grep a few `wp_options` values for old URL
      (should be none): `wp db query "SELECT option_value FROM
      <TABLE_PREFIX>options WHERE option_name IN ('home','siteurl')"`.
- [ ] Compare a **DB row count** sanity: `wp db query "SELECT COUNT(*) FROM
      <TABLE_PREFIX>posts"` matches source count (from inventory).
- [ ] Load test (optional for big sites): hit the site with a handful of
      concurrent requests (`ab -n 200 -c 10 https://<PREVIEW_HOST>/`) —
      confirms PHP/DB can handle traffic at the new infra.
- [ ] Any custom integration (webhooks, third-party APIs): check their
      configured URLs match the new domain or are still correct.

### 7.4 Fix loop

- Any FAIL: fix → re-run the full checklist → re-confirm. Common fixes:
  permissions (§4.5), PHP extensions (`php -m` vs source), DB creds,
  search-replace re-run, `.htaccess`/nginx rules, object-cache flush,
  missing uploads (re-rsync `wp-content/uploads`).
- Keep the **untouched staging copy** (files + raw dump) so a bad change
  can be reverted (R3/R4).

---

## 8. Phase 7 — Cutover: Branch A (Single-Run / Maintenance Page)

> Choose this if D1 = single run-through. Downtime = duration of this phase.
> **Requires: all Phase 6 checks passed** (or at least the critical ones; do
> NOT skip the front-page/admin/login/media checks).

### 8.1 Pre-flight (5 min)

- [ ] Confirm maintenance-window approval (D4).
- [ ] **Notify** (D5) — announce maintenance window.
- [ ] Confirm source still serving production; confirm destination still
      passing Phase 6 checks.
- [ ] Have the rollback plan (R1) + backup location ready and confirmed.

### 8.2 Enable the maintenance/upgrade page

**WRITE** — Two independent mechanisms (do both; belt and braces):

1. **Static web-server page (recommended, survives everything):** replace
   the site root with a static `index.html` ("We'll be right back —
   upgrading…") and/or serve a `503` via the web server config with a
   `Retry-After` header. This is the "upgrade page" the operator mentioned.
   Simplest robust form:
   ```nginx
   # nginx: location / { try_files /maintenance.html =503; }
   ```
   or Apache: a `maintenance.html` + `.htaccess` `RewriteRule ^$
   /maintenance.html [L]` (or `ErrorDocument 503`).
2. **WordPress maintenance file:**
   `echo '<?php $upgrading = time(); ?>' > wp-content/.maintenance` — makes
   WP show the "Briefly unavailable" message to non-logged-in users. (Works
   only while WP can run at all.)

> **Order:** put the static page up first (catch-all), then the WP-level
> file. On completion, remove in reverse.
>
> Rollback: remove the maintenance artifacts in reverse order — source
> resumes serving.

### 8.3 Freeze writes & take the final snapshot

- [ ] **WRITE** — Stop write-sources (or accept they're blocked by the
      maintenance page). If you used the static page at the web-server
      level, WP never sees traffic, so no new writes.
- [ ] **WRITE** — **Final DB dump** of the source (§5.1) — this is now the
      authoritative final DB.
- [ ] **WRITE** — **Final file sync** of `wp-content/uploads` (and any
      changed files) from source → dest (rsync delta, §4.2).

### 8.4 Import final data to destination

- [ ] **WRITE** — Import the final dump into the destination DB (§5.3).
      Rollback: R3.
- [ ] **WRITE** — Re-run the serialization-safe search-replace **if and only
      if** the URL transformation was pending (domain-change case) or the
      staging→real-domain flip is needed (§5.4). If domain is unchanged and
      preview used `/etc/hosts`, **no replace needed**. Rollback: R3.
- [ ] **WRITE** — Flush object cache + transients (§9.4).
- [ ] Re-run the **critical** Phase 6 checks (front page 200, admin login,
      media, one key flow) on the destination using the **real domain via
      `/etc/hosts`** (so you test exactly what users will see).

### 8.5 Flip the traffic

- [ ] **WRITE** — **Same domain, same IP pool / same server class:** if the
      destination IP is what DNS already points at (e.g. you control the
      record and it's the same), just remove the maintenance page.
- [ ] **WRITE** — **Different IP:** now that the destination is verified
      under the real domain via `/etc/hosts`:
      - If you can change DNS quickly (low TTL already set in Phase 2),
        update the A/CNAME record to the destination IP (§9.1) and let
        propagation proceed.
      - If DNS change is slow/impossible in-window, the cutover is
        effectively "make the destination serve the real domain from a
        machine that's reachable" — this usually means the DNS change IS
        the cutover, so Branch A with a different IP and un-lowered TTL may
        mean you wait on propagation. **This is why Branch B lowers TTL in
        advance.** For Branch A, plan the DNS change at the start of the
        window or pre-lower TTL the day before (§3.1/N3).
  Rollback: revert the A/CNAME record to the source IP (R2) and purge any
  CDN cache.
- [ ] **WRITE** — Once traffic points at destination, **remove the
      maintenance page** (reverse §8.2 order): remove `.maintenance`,
      restore normal vhost to serve the real site.
- [ ] Confirm real-domain requests now hit the destination (see §10.1 for
      how to verify which server answered).

### 8.6 Branch A completion

- [ ] Full post-cutover verification (§10). Then proceed to §10.3
      decommissioning. **Branch A is done once Phase 9 passes.**

---

## 9. Phase 8 — Cutover: Branch B (Zero/Near-Zero Downtime, DNS Cutover)

> Choose this if D1 = zero/minimal downtime. The site remains live on the
> source throughout staging. Downtime is only the propagation/re-sync
> window, usually seconds-to-minutes. **Requires: Phase 6 checks passed; DNS
> TTL pre-lowered; delta-sync path pre-tested; source SSH (or DB access)
> for the final dump.**

### 9.1 Pre-cutover DNS preparation (24–48h before)

- [ ] **WRITE** — **Lower TTL** on the domain's A/CNAME record to `300`
      (5 min) or less at the DNS provider (N3). Verify with `dig <DOMAIN>`
      / `nslookup`. Rollback: restore original TTL.
- [ ] If **CDN proxied (orange cloud)**: TTL is irrelevant (CDN manages it);
      instead plan to **purge cache** after the cutover and consider
      temporarily switching to DNS-only (grey cloud) during the flip so the
      edge doesn't serve stale origin. (Trade-off, see §12.)
- [ ] Confirm the destination IP is stable and reachable from the wider
      internet (firewall open on 80/443 — T7).
- [ ] **Pre-test the delta sync** (dry run today): run the exact final-sync
      commands you'll run at cutover against current data and confirm they
      complete within the budgeted window (see §9.2). This de-risks the
      actual day.

### 9.2 At cutover — final delta sync (the "deltas")

The goal: make the destination match the source as of time T, in the
shortest window possible, because the source is still live until DNS flips.

1. **Final file delta (fast, rsync only changed bytes):**
   ```bash
   rsync -avz --partial --progress --delete <SOURCE_WP_ROOT>/ <DEST_SSH>:<DEST_WP_ROOT>/
   ```
   (`--delete` removes staging-only leftovers; confirm your excludes don't
   nuke uploads — keep the same excludes as Phase 3.)
2. **WRITE** — **Final DB dump + import (the true downtime window):**
   ```bash
   wp db export /tmp/final-$(date +%s).sql --single-transaction --quick
   gzip /tmp/final-*.sql
   scp /tmp/final-*.sql.gz <DEST_SSH>:/tmp/
   # On dest:
   gzip -dc /tmp/final-*.sql.gz | mysql -h <DEST_DB_HOST> -u <DEST_DB_USER> -p <DEST_DB_NAME>
   ```
   - Ideally, **briefly suspend writes** on the source for just the dump
     (e.g. put the WP `.maintenance` file up for the ~seconds of the dump,
     or rely on `--single-transaction` snapshot + accept a tiny re-sync
     below). With `--single-transaction` the dump is a consistent snapshot;
     writes after the snapshot are the residual delta.
   - If you *cannot* suspend writes, plan for a **second short dump after
     DNS flip** (§9.4).
3. **WRITE** — Re-run any URL search-replace if the transformation is
   pending (same rules as §5.4/§8.4). Rollback: R3.
4. **WRITE** — Flush caches (§9.4).

### 9.3 The DNS flip

- [ ] **WRITE** — Change the A/CNAME record to the destination IP (or the
      appropriate record per §2.5/N1–N3). Rollback: revert record to source
      IP (R2).
- [ ] **WRITE** — (CDN proxied) purge cache / ensure it re-fetches from the
      new origin.
- [ ] Start the clock on propagation; expect up to the old-TTL period + a
      few minutes, usually much faster at TTL=300.

### 9.4 Re-sync during propagation (the "re-migrate the database" step)

Because traffic still hits the source while DNS propagates (recursors with
old cached TTL, users with open connections), the source may receive writes
after the cutover dump. To not lose them:

- [ ] **After DNS flip**, watch propagation (`dig <DOMAIN>` from a few
      recursors / `dnschecker.org`). Once the *overwhelming majority*
      resolves to the destination (or after the old-TTL window has
      elapsed), do a **final, quick, write-catch-up dump+import**:
  ```bash
  # Source (dump only what changed — simplest: a fresh full dump; it's small at this scale):
  wp db export /tmp/catchup-$(date +%s).sql --single-transaction --quick
  scp ... ; gzip -dc ... | mysql -h <DEST_DB_HOST> -u <DEST_DB_USER> -p <DEST_DB_NAME>
  ```
- [ ] **IMPORTANT danger:** If you re-import the *whole* DB after the
      destination has already been live and receiving its own writes
      (comments/orders created directly on the new site), a full overwrite
      will **lose** those new-site writes. Only re-import the whole DB if
      the destination has NOT yet taken writes. Two safe patterns:
  - **Pattern 1 (recommended):** flip DNS when you're confident propagation
    is fast, keep the destination effectively read-only until the catch-up
    import completes (block web writes with a temporary maintenance file on
    the destination during the propagation+re-sync window, or accept the
    tiny gap). Then remove the block.
  - **Pattern 2 (full overwrite is safe):** if the destination is only
    reachable via staging and has no real traffic until DNS flips, then the
    catch-up full import is safe — but do it *before* DNS has effectively
    switched traffic, or you risk the overwrite race.
- [ ] **Alternative for change-heavy sites (safer than whole-DB
      re-import):** re-import only the delta. If you can't get a real binary
      log/tool, the pragmatic approach is: at cutover take the dump, and if
      the destination hasn't served real traffic yet, the catch-up full
      import is fine. For most WP sites (content, comments, orders), a
      short propagation window means delta ≈ 0; the whole-DB catch-up is
      only for the "big slow propagation / high write rate" edge — handle
      by deciding explicitly in Phase 1 which pattern you'll use (record it
      in the inventory).
- [ ] **Re-sync files during propagation too** if uploads can change (users
      uploading media): repeat the rsync delta once propagation is
      complete.
- [ ] **WRITE** — Flush object cache & transients on the destination
      **after** the catch-up import.

### 9.5 Verify live, then remove the staging surface

- [ ] Once propagation is (mostly) complete, run **Phase 9 post-cutover
      verification** (§10) against the real domain.
- [ ] **WRITE** — Remove the staging hostname from the destination vhost
      (or keep it but confirm it can't be indexed / is firewalled). Remove
      `/etc/hosts` entries from testing machines.
- [ ] **WRITE** — Flush destination caches once more. Branch B complete.

---

## 10. Phase 9 — Post-cutover verification & decommissioning

### 10.1 Verify traffic actually hits the destination

```bash
# Local DNS: what does the record resolve to now?
dig +short <DOMAIN> ; nslookup <DOMAIN>

# Which server answered? (destination IP should appear in DNS, and the request should reach it)
curl -sS -o /dev/null -w "%{http_code} %{remote_ip}\n" https://<DOMAIN>/
# Confirm remote_ip == destination IP, not source.

# If a unique marker helps: check a server-identity header or the TLS cert issuer (should be the destination's cert).
echo | openssl s_client -connect <DOMAIN>:443 -servername <DOMAIN> 2>/dev/null | openssl x509 -noout -issuer
```

### 10.2 Full post-cutover checklist

- [ ] `curl` front page returns **200** and correct content from the
      destination IP.
- [ ] Admin login works on the real domain.
- [ ] Spot-check key pages, a post, an archive, media files.
- [ ] **Media uploads still referenced correctly** — check an image URL
      returns the file.
- [ ] Search-replace spot-checks (no old-domain URLs in
      `wp_options`/content where expected).
- [ ] **Forms/comment/transaction paths** work end-to-end (one real
      submission in staging-like manner, e.g. a test comment or test order
      that you then delete).
- [ ] Cron jobs fire on the destination (`wp cron event run --all`); real
      system cron entries ported (S9) and confirmed in `crontab -l` / the
      scheduler.
- [ ] **Object cache** flushed and connected; no stale data.
- [ ] SSL valid on the real domain (issuer matches destination).
- [ ] CDN (if any): cache purged; origin set to destination (S10/N4).
- [ ] **Email** (if moved): send test mail; verify SPF/DKIM if records were
      changed (N5) — often email should *stay* on the old server and NOT
      move; decide explicitly.
- [ ] Check both error logs (`wp-content/debug.log`, PHP error log) for new
      errors after real traffic arrives.
- [ ] Verify no `.maintenance` file left on the destination (Branch A) —
      remove if present.

### 10.3 Keep the source warm (the safety net)

- [ ] Do **not** decommission the source yet. Keep it running, reachable,
      and able to serve (the simplest, strongest rollback is "point DNS
      back").
- [ ] Set a **watch period** (default recommendation: 3–14 days, matching
      any high-traffic event / billing cycle / update cycle). During this
      period:
      - Monitor destination logs & uptime.
      - Keep the source's final DB dump + files archived off-box.
- [ ] After the watch period (or per operator decision, D5), decommission:
      - Stop accepting traffic on the source (move DNS permanently if still
        on old, or leave as-is if DNS already points at dest).
      - Take a **final source backup** and archive it off-box.
      - Cancel/repurpose the source server per operator instruction.
      - Remove staging hostname records, `/etc/hosts` test entries,
        temporary firewall rules.

---

## 11. Phase 10 — Rollback

> Rollback is a *planned capability*, triggered by the rules in §2.3.
> Execution differs by branch.

### 11.1 Rollback before cutover (both branches)

- The source was never touched (still live). **Rollback = do nothing /
  cancel.** Destroy/repurpose the destination staging copy. Zero user
  impact.

### 11.2 Rollback during/after Branch A cutover

1. Put the maintenance page back up (§8.2) to stop users seeing a broken
   site.
2. Restore source serving production: if DNS changed, revert the A/CNAME to
   the source IP; if only the maintenance page was involved, remove it.
3. The source never stopped having the real data, so after reverting
   traffic, the source is authoritative again.
4. Preserve the failed destination (files + dump) for diagnosis; record
   what failed and why.

### 11.3 Rollback after Branch B cutover (DNS flip-back)

1. **Stop the bleeding:** set DNS back to the source IP (TTL already low →
   fast).
2. **Data reconciliation:** the source may have missed writes that landed
   on the destination during the flip window. If that's acceptable (usually
   tiny), proceed; if not, restore from the best point-in-time (the
   catch-up dump, or the source's own state) and accept a small gap.
   Document the data gap explicitly.
3. **Destination:** leave it running as a staging/dev instance for
   investigation; remove from the public path.
4. Re-plan and retry after diagnosis.

### 11.4 Rollback via backup restore (R1, worst case)

- Restore the source from the off-box backup (files + DB) exactly as
  verified in §3.1.
- Restore DNS to source IP.
- Everything else follows the above.

---

## 12. Master risk, caveat & drawback register

> Ordered by likelihood × impact. Mitigations are concrete actions in
> earlier phases. See also `notes/` for run-verified incidents.

| # | Risk / Caveat | Likelihood | Impact | Detection | Mitigation |
|---|---------------|-----------|--------|-----------|------------|
| 1 | **Serialized-data corruption** from naive search-replace (sed, careless SQL UPDATE) | Med (if using sed) / Low (WP-CLI) | High — broken widgets/plugins/settings | `wp db check`; spot-check options; site looks broken | Always `wp search-replace` / Better Search Replace; `--precise`; dry-run first; skip `guid`; test after (§5.4) |
| 2 | **DB dump not consistent** (writes during mysqldump without `--single-transaction`) | Med | Med | Referential mismatches, missing rows | `--single-transaction` on InnoDB; Branch B write-suspend or catch-up (§5.1, §9.2) |
| 3 | **Delta overwrite race (Branch B)** — re-importing whole DB over a destination that already took writes | Med (busy site) | High — lost new-site data | Timeline confusion | Decide Pattern 1 vs 2 up front (§9.4); keep destination write-blocked during re-sync, or use catch-up full import only before traffic switches |
| 4 | **File permissions/ownership** wrong on destination (uploads not writable, 500 errors) | High | Med-High | 500s; media fails; plugin can't write | Explicit chown/chmod step (§4.5); test upload via admin |
| 5 | **`.htaccess`/nginx rewrites not ported** → pretty URLs 404, or redirect loops | High | Med | 404s on posts; `/wp-admin` redirect loops | Port `.htaccess` or nginx `try_files` + PHP-FPM block (§6.2, §A.7); test permalinks (§7.3) |
| 6 | **PHP version mismatch** — plugins/themes incompatible with dest PHP | Med | Med-High | Fatal errors on pages/admin | **Pin PHP like-for-like, never upgrade during migration** (S4/T3, §3.2); check `wp plugin list` against known compat; staging test (§7.2) |
| 7 | **MySQL/MariaDB version or collation mismatch** | Med | Med | Import errors; weird sorting; charset mojibake | **Pin MariaDB/MySQL like-for-like, never upgrade during migration** (S5/T4, §3.2); compare versions/collation (§5.3); match `utf8mb4` |
| 8 | **Old domain URLs baked into serialized options / object cache / page caches** | Med | Med | Links/images to old URL after cutover | Search-replace covering all tables; flush object cache + transients + any page cache (§5.4, §9.4) |
| 8b | **Source filesystem paths baked into serialized options** (EWWW aux paths, Freemius `abspath`, SiteOrigin widget paths, `recently_edited`) — survives even with an unchanged domain | High (if dest path differs) | Med | EWWW optimization breaks; Freemius paths wrong; SiteOrigin widget errors | Detect in Phase 0 (`LIKE '%/var/www/%'` on `wp_options`); serialization-safe path search-replace on dest (§5.4); pick dest path deliberately |
| 8c | **`wp search-replace --recurse-objects` skips serialized objects of unloaded plugin classes** (MailChimp, WPML, WCML, Freemius) — old URLs stay in plugin settings/cache | High (plugin-heavy sites) | Low-Med (not front-end; correct again once domain reverts at cutover) | `Skipping an uninitialized class` warnings; leftover scan (§5.4) | Accept for plugin-internal data; to fix at staging, load the plugin classes during the replace; full re-dump at cutover re-normalises anyway |
| 9 | **DNS propagation longer than expected** (didn't lower TTL, or CDN edge) | Med | Med | Mixed traffic hitting both servers | Pre-lower TTL 24–48h (§9.1); CDN purge; Branch B design absorbs this (§9.4) |
| 10 | **CDN serving stale/cached content from old origin** | Med | Med | Users see old site after cutover | Purge CDN cache; update origin; optionally grey-cloud during flip (§9.1) |
| 11 | **Email breakage** (moving web but not mail, or SPF/DKIM tied to source) | Med | Med-High (business impact) | Mail failing/delivered to junk | Decide mail scope explicitly (S11/N5); update SPF if IP changes; test after cutover |
| 12 | **Disk full on destination** during import/transfer | Med | High | Import fails halfway; corrupted state | Pre-check disk (T6 ×1.5); monitor `df -h` during phases |
| 13 | **Transfer interruption** (rsync/scp over flaky link; big uploads) | Med | Med | Partial files | rsync `--partial`/`-v`; re-run until clean; gzip dumps (§4.2, §5.1) |
| 13b | **Memory blowup relaying a multi-GB binary stream through a text-piping shell** (PowerShell 5.1 buffers native output in RAM) | High (if the orchestrator relays via such a shell) | Med-High (OOM, stalled transfer) | RAM climbs with stream size | Run pipes natively (`cmd /c`, bash/WSL, or a single Linux host); batch transfers; avoid relaying at all when possible (§4.6) |
| 14 | **Migration-plugin upload/execution limits** (archive too big, memory/timeouts) | High (large sites, L1) | Med | Installer fails | Use SSH method when possible; raise `upload_max_filesize`/memory; chunk or use host import tool (M3/M4) |
| 15 | **`.maintenance` file left behind** → site stuck in "briefly unavailable" | Low | Med | Site shows maintenance for everyone | Remove in reverse order (§8.2/§8.5); post-cutover check (§10.2) |
| 16 | **Salts/cookies:** users logged out at cutover (salt shuffle) | Certain | Low | Mass re-login | Expected; communicate it (D5); keep salt shuffle optional if you prefer continuity |
| 17 | **Hardcoded URLs in theme/plugin/custom code files** (not just DB) | Med | Med | Links/redirects wrong, but files search-replace can't fix DB-only | `grep -rl 'old-domain' wp-content/themes wp-content/plugins wp-content/mu-plugins` before finalizing; fix or accept |
| 18 | **Multisite mishandled** (subsite tables, `wp_blogs`/`wp_site`, network search-replace) | Low-Med (multisite only) | High | Broken network/subsites | Detect S6; use `--network` search-replace; port `wp_blogs`; test each subsite |
| 19 | **Object-cache drop-in copied with old backend config** (redis host/port) | Med | Med | Fatal connect errors / stale data | Update cache config for dest; flush; test `redis-cli ping` (§4.5, §7.2) |
| 20 | **Third-party services / webhooks pointed at old domain** | Med | Med | Payments, CRM, analytics stop | Check integrations (S15); update endpoints; test (§7.3) |
| 21 | **`.htaccess` with AbsolutePaths / symlinks with absolute targets** | Med | Med | Broken paths on dest | Preserve symlinks (`rsync -a`), fix absolute paths, re-test (§4.2) |
| 22 | **Branch A "upgrade page" itself broken** (web server down / config error) | Low | High (if it hides a working site) | Users see nothing | Test maintenance page rendering before starting (§8.2) |
| 23 | **No rollback tested / backup unverified** | Low (if process followed) | Catastrophic | — | §3.1 mandatory verification; §2.3 plan signed off |
| 24 | **Destination `wp-config.php` clobbered by a later `--delete` re-sync from source** (source config overwrites dest DB creds; or worse, `--delete` removes the volume's wp-config entirely) | High (re-sync flows) | High (site 500 / DB connection broken at cutover) | `DB_HOST`/salts revert to source; site 500 | Exclude `wp-config.php` from ALL rsyncs including the final delta; never delete it from the mirror with `--delete` (§4.1, verified incident 2026-08) |
| 25 | **Stale object cache after DB re-import serves pre-import option values** (file object cache holds an `alloptions` snapshot taken mid-rebuild) | Med | High (silent broken behavior — e.g. login loops, plugin installer re-runs) | `get_option()` returns wrong value while DB looks right; wp-cli and php-fpm disagree | After ANY DB import, purge the object cache (`rm -rf wp-content/cache/*` + `wp transient delete --all`) and verify through HTTP, not just wp-cli (§9.4, verified incident 2026-08) |
| 26 | **Import reports EXIT=0 but silently did nothing** (transient pipe/exec issue) | Low | High (you cut over on stale data) | Table counts unchanged; content probes find old data | Always verify import effect with a content probe (`SELECT COUNT(*)` on a known table / grep a marker string), not just exit code (§5.3, verified incident 2026-08) |

### Inherent drawbacks of each approach (be honest with the operator)

- **Branch A:** guarantees a maintenance window; the window scales with
  DB/file size; any human error during the window = real downtime. Best for
  small sites or sites with a natural low-traffic window.
- **Branch B:** more moving parts (TTL, propagation, delta re-sync,
  overwrite race). The added complexity is the price of near-zero downtime.
  **Not appropriate** when DNS is controlled by someone slow, when the site
  has constant high-write traffic with no suspend option, or when you don't
  have SSH/dump access for the delta.
- **Plugin method (M3):** least control, adds third-party code, upload
  limits, and its search-replace quality varies; always verify after. Only
  for L1/urgency.
- **"Zero downtime" is a goal, not a promise.** Realistically:
  seconds-to-minutes. Set expectations accordingly (D4).

---

## Appendix A — Copy-paste command kit

> All commands assume Linux servers and bash. Windows/jump-host variants
> noted where relevant.

### A.1 Site/file backup (off-box)
```bash
# Source: create tarball
tar czf site-backup-$(date +%F).tar.gz -C /var/www site/
# or rsync a mirror to an off-box location
rsync -avz --partial /var/www/site/ backup-host:/backups/site/
```

### A.2 DB dump (consistent)
```bash
# WP-CLI (preferred — reads wp-config)
cd /var/www/site && wp db export site-$(date +%F).sql --add-drop-table --single-transaction --quick
gzip site-$(date +%F).sql
# Raw mysqldump
mysqldump --single-transaction --quick --add-drop-table -h HOST -u USER -p DB > site-$(date +%F).sql && gzip site-$(date +%F).sql
```

### A.3 DB import (dest)
```bash
gzip -dc site-2026-07-01.sql.gz | mysql -h DEST_HOST -u DEST_USER -p DEST_DB
# or via WP-CLI from the dest site dir:
wp db import site-2026-07-01.sql
```

### A.4 URL change / search-replace (dest, serialization-safe)
```bash
wp search-replace 'example.com' 'newexample.com' --all-tables-with-prefix --precise --recurse-objects --skip-columns=guid --dry-run
wp search-replace 'example.com' 'newexample.com' --all-tables-with-prefix --precise --recurse-objects --skip-columns=guid
wp search-replace 'https://example.com' 'https://newexample.com' --all-tables-with-prefix --precise --recurse-objects --skip-columns=guid
wp option update home 'https://newexample.com'
wp option update siteurl 'https://newexample.com'
wp transient delete --all
```

### A.5 Permissions (dest)
```bash
chown -R www-data:www-data /var/www/site-dest/     # match dest web user
find /var/www/site-dest -type d -exec chmod 755 {} \;
find /var/www/site-dest -type f -exec chmod 644 {} \;
chmod 755 /var/www/site-dest/wp-content/uploads
```

### A.6 Salt shuffle (dest)
```bash
wp config shuffle-salts
# or paste fresh keys from https://api.wordpress.org/secret-key/1.1/salt/
```

### A.7 nginx WordPress config essentials
```nginx
server {
  listen 443 ssl http2;
  server_name example.com www.example.com;
  root /var/www/site-dest;
  index index.php index.html;
  # TLS certs here (T10)

  location / {
    try_files $uri $uri/ /index.php?$args;
  }
  location ~ \.php$ {
    include fastcgi_params;
    fastcgi_pass unix:/run/php/php8.2-fpm.sock;   # match dest PHP version
    fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
  }
  location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
    expires 7d; access_log off;
  }
}
```
(Apache: `.htaccess` copied from source + `AllowOverride All` in the vhost.)

### A.8 Verification commands
```bash
wp core is-installed
wp core version
wp db check
wp db size
wp plugin list --status=active
wp theme list --status=active
wp cron event run --all
wp transient delete --all
wp db query "SELECT option_value FROM wp_options WHERE option_name IN ('home','siteurl')"
dig +short example.com
curl -sS -o /dev/null -w "%{http_code} %{remote_ip}\n" https://example.com/
```

---

## Appendix B — Site health snapshot template

> Fill this in during Phase 0. Store in the execution's `inventory.md` (do
> not paste secrets — reference "see secrets/" of the execution).

| Field | Value | Source (operator/inspection) |
|-------|-------|------------------------------|
| Migration branch (A/B) | | D1 |
| Rollback plan (R1–R4) | | §2.3 |
| Domain(s) | | D3/N1 |
| Source hosting / dest hosting | | S1/T1 |
| Source SSH level / dest SSH level | | §1.4 |
| WP version / Multisite? | | S6 |
| PHP version (source/dest) | | S4/T3 |
| MySQL/MariaDB (source/dest) | | S5/T4 |
| Web server (source/dest) | | S3/T3 |
| Active plugins | | S7 |
| Active theme / custom theme | | S7 |
| Object cache (type/config) | | S8/T9 |
| Cron (WP/system; crontab entries) | | S9 |
| CDN (provider/proxied?) | | S10/N4 |
| Mail (server/records/SPF/DKIM) | | S11/N5 |
| SSL (type/issuer/wildcard) | | S12/T10 |
| Total site size / uploads size | | S13 |
| DB size / table count | | S13 |
| `.htaccess` / custom rules | | S14 |
| Non-WP scheduled jobs/writers | | S15 |
| DNS provider / TTL / records | | N1–N3 |
| Staging preview method | | T8 / §5.5 |
| Delta-write pattern chosen (B) | | §9.4 |
| Maintenance window / downtime budget | | D4 |
| Approver / contacts | | D5 |
| Final DB dump file + checksum | | Phase 7/8 |

---

## Authoring rules (this playbook)

- Steps are copy-paste executable with `<PLACEHOLDER>` tokens.
- Every step that WRITES to a production system is flagged **WRITE** in
  bold. Reads need no flag.
- Rollback instructions accompany every write step; Phase 10 is the
  branch-level rollback.
- Run findings go to the run's `notes.md`; promotion into `notes/` (and
  rarely this file) happens after the run, with operator approval. Never
  edit this file mid-run.

*End of playbook. After Phase 0–2 are answered, the plan becomes a filled
runbook. Run phases in order; never skip verification.*
