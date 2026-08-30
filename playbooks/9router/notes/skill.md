# 9Router skill — fetch live each run

The upstream skill is **not bundled** in this repo. The agent fetches it
live at the start of every run (playbook §0) so the API contracts are always
current.

Upstream source:

```
https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router/SKILL.md
```

Save a snapshot to `logs/<timestamp>-00-skill.md` for the run record.

## What the skill covers

- `NINEROUTER_URL` / `NINEROUTER_KEY` env contract
- `GET /api/health` → `{"ok":true}` (no auth)
- `GET /v1/models` [+ `/v1/models/image|tts|embedding|web|stt|image-to-text`]
  → `{ object:"list", data:[{id, owned_by, kind?}] }` with combos as `owned_by:"combo"`
- `POST /v1/chat/completions` and other OpenAI-compatible routes via `Authorization: Bearer <KEY>`
- Error signals: `401` (refresh key), `400 Invalid model format`, `503 All accounts unavailable`

## Capability skills (fetch on demand when testing that capability)

Listed inside the main SKILL.md:

| Capability | Raw URL |
|---|---|
| Chat / code-gen | `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router-chat/SKILL.md` |
| Image generation | `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router-image/SKILL.md` |
| Text-to-speech | `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router-tts/SKILL.md` |
| Speech-to-text | `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router-stt/SKILL.md` |
| Embeddings | `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router-embeddings/SKILL.md` |
| Web search | `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router-web-search/SKILL.md` |
| Web fetch | `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router-web-fetch/SKILL.md` |

Rule: before any management step that touches the 9Router API, fetch the
main SKILL.md. Before a probe of a specific capability (e.g. a chat smoke
test), fetch that capability's SKILL.md and follow its request shape verbatim.
