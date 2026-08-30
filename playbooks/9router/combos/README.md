# Combos Baseline — 2026-08-30

Snapshot of the 90 models and 5 combos as configured on `http://development-9router-fe01c0-62-171-191-174.sslip.io` (remote existing instance, execution `executions/9router/` no suffix).

This is the **starting point for next time** — committed in the playbook so future runs can diff against it. Update by re-running the generator and overwriting these files (or via Dashboard → Combos → Export, then copy to here).

## Source

- `models.json` / `models.csv` — `GET /v1/models` `90` ( `ocg 24`, `cmc 24`, `openrouter 18`, `cf 13`, `ollama 6`, `gemini 4`, `combo 5`) captured `2026-08-30T18:18` to `executions/9router/models.json:1`.
- Scores from `https://artificialanalysis.ai/leaderboards/models` `624` `Intelligence Index v4.1.1` + `CostPerTask` (`intelligenceIndexCostPerTask.cost.total`). Blank where unbenchmarked (8: `laguna-*`, `hy4-preview`, `dots-3`, `lyria-*`, `openrouter/free`). `muse-spark-1.2-contributor` cost overridden to `0.02` (discounted $0.10/$0.20) so it sorts cheapest.

## Combos (order as applied)

All combos were `PUT/POST /api/combos` via `POST /api/auth/login` (JWT `auth_token` from `executions/9router/secrets/dashboard-password.txt:1` — gitignored).

| Combo | File | Count | Filter | Ordering (as applied) | Id |
|-------|------|-------|--------|-----------------------|----|
| `free` | `free.json` / `free.csv` | 41 | All free `openrouter/cf/ollama/gemini` (`ocg/cmc` excluded) | `intelligence desc` (highest first, cost irrelevant), blanks last | `824080de-eb9a-4c51-88dc-5ee5f098a440` |
| `coding-pro` | `coding-pro.json` / `coding-pro.csv` | 15 | `intelligence ≥50` | `cost asc → free before paid (tie) → intelligence desc` (muse `0.02` top, then `glm-5.3-flash 0.086`) — order as edited in `executions/9router/combos/coding-pro.csv:1` | `d5629432-1d39-4508-827a-63eaa6af33c6` |
| `coding-med` | `coding-med.json` / `coding-med.csv` | 35 | `intelligence ≥40` | same `cost asc` ordering, order as edited (`executions/9router/combos/coding-med.csv:1`) | `c54e2cd1-478d-40ab-9e58-2d2dc5853df9` |
| `coding-low` | `coding-low.json` / `coding-low.csv` | 50 | `intelligence ≥30` | same `cost asc` ordering, order as edited (`coding-low.csv:1` — `mimo-v2.5 0.010`, `mimo-pro 0.033`, `hy3 0.035` top) | `3df4a691-8414-441b-bb70-1e91c20b2f10` |
| `vision` | `vision.json` / `vision.csv` | 26 | `capabilities.vision=true` | `cost asc` (`mimo-v2.5 0.010` → … → `gemma` ) | `3d3ef74d-becb-4eab-ad04-7d8529ed763e` |

All `*.json` have `models: [id]` (apply order) and `members: [{id, owned_by, intelligence, costPerTask, aa_slug, vision, contextWindow}]` plus `intelligence`/`costPerTask` from AA. `*.csv` has `rank` matching `models` order (re-sequenced after manual edits).

## Free before paid

Applies to all levels as secondary sort after `cost` (so cheaper models first, but within same cost free preferred). For `free` combo all are free, so `intelligence desc`.

## Updating

- Add providers/models via Dashboard, then `GET /v1/models` → refresh `models.json` here, or run `python playbooks/9router/scripts/generate-configs.py` (live fetch) and `python scripts/generate-threshold.py` (with your thresholds 50/40/30) then copy the edited `executions/9router/combos/*.json|*.csv` to here.
- Or edit `executions/9router/combos/*.csv` order directly, then `python fix-ranks.py` to re-sequence ranks and sync `*.json`.

## Generated configs

`executions/9router/generated/` (gitignored) is built from live `GET /v1/models` via `playbooks/9router/scripts/generate-configs.py:1` — contains `opencode.json`, `hermes-config.yaml`, `codex-config.toml`, `claude-settings.json`, `generic-env.sh` copy-paste for remote servers. The baseline combos here are the source of truth for `provider/model` ids used in those generated configs.
