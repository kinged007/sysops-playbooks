# Lessons: hermes-deploy

Read before planning. Each item changed a past run's plan.

## Dokploy API (v0.29.x, dot-notation routes, `x-api-key` header)

- `compose.create` defaults to `sourceType: github`. Raw compose content needs
  `compose.update {sourceType: "raw"}` before the first deploy, or the deploy
  fails with "Github Provider not found".
- Compose file and env are SEPARATE stores. `compose.update {composeFile}`
  never touches env; `compose.update {env}` never touches the file. Pushing
  one and redeploying runs stale values for the other.
- Dokploy refuses a deploy while a domain points at a service missing from the
  compose file. Order: delete the domain FIRST, then push/deploy. Same rule in
  reverse does not apply (adding service then domain is fine).
- Dokploy auto-injects `dokploy-network` into services with domains. Do not add
  Traefik labels or manual networks to the compose file; keep one private
  bridge network and let Dokploy handle the rest.
- Persistence must use relative binds (`../files/...`, survives redeploys).
  Absolute host paths are cleaned on redeploy.
- Deploy command is effectively `docker compose -p <app> -f docker-compose.yml
  up -d --build --remove-orphans` on the remote.

## Validation

- `docker compose config` tolerates duplicate YAML keys (last-wins). A file
  that passes it can still fail Dokploy ("Compose file not found").
  Strict-validate every file: `python3 -c "import yaml; yaml.safe_load(...)"`.

## Hermes image contract (nousresearch/hermes-agent)

- Data dir is `/opt/data` (== `$HOME` inside the container): `.env`,
  `config.yaml`, sessions, skills. Single source of truth; image is stateless.
- Never override `entrypoint:` (s6-overlay needs PID 1; without it there is no
  supervision, no volume-ownership repair, and zombie reaping breaks). Never
  `docker exec` writers as root into data files — root-owned files break the
  runtime user. Set `HERMES_ALLOW_GATEWAY...` flags only intentionally.
- The entrypoint chowns the data dir to its runtime user at boot. Any
  co-writer container MUST run as the same uid, or reads/writes fail.
- The s6 dashboard slot reads `HERMES_DASHBOARD` (and only it decides
  startup) from PROCESS env via `with-contenv` — values in `/opt/data/.env`
  do not start it. Auth vars reach the app from process env too. Keep
  infra bootstrap creds in Dokploy env; agent secrets in `/opt/data/.env`.
- Dashboard fails closed: non-loopback bind without an auth provider refuses
  to start. Basic-auth provider suits trusted networks behind TLS, not raw
  public internet (use OIDC there).
- Gateway restart (dashboard System page, or container restart) is required
  after key changes. Never run two gateways against one data dir.
- Resource floor: 1 GB RAM / 1 CPU minimum; 2–4 GB with browser tools.
  WAL SQLite is fine on XFS loop mounts (real block fs).

## ttyd terminal contract (tsl0922/ttyd ≥ 1.7)

- `-w` = working dir, `-W` = allow writing (terminal is READONLY by default).
  The old `-W /dir` form is silently misparsed and can disable auth.
- Image entrypoint is tini; `command:` must start with `ttyd`.
- `user:` accepts numeric uid; unlisted uids show `I have no name!`. Fix the
  prompt with a volume-persisted `--rcfile` (sets PS1 explicitly) rather than
  fighting passwd entries. Silence the bashrc sudo-hint `groups` error with a
  `$HOME/.hushlogin` guard file.
- Shell needs no curl/wget/images tooling: bake a derived image
  (`FROM tsl0922/ttyd:<tag>` + editors, local tag, `pull_policy: never`)
  instead of runtime installs, which die on redeploy.

## Storage

- Host ext4 + overlay2/extfs: `docker --storage-opt size=` is silently
  ignored (check `docker info`: Backing Filesystem). Hard caps need the XFS
  loop image mounted on the app's `files/` dir (docs-safe relative bind),
  with `pquota` + fstab persistence. The image size itself is the cap.
- Mount XFS only over empty dirs; `chown` the mount to the agent uid after
  mounting; containers need a restart to pick up a new underlying mount.
- Dokploy Volume Backups cover named volumes, NOT `../files` binds — back up
  the XFS image at host level on a schedule.
