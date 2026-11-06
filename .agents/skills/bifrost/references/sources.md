# Bifrost reference documentation (fetch live, never cache)

Docs index: `https://docs.getbifrost.ai/llms.txt`
Full OSS index (151 pages): `https://docs.getbifrost.ai/_llms/oss.txt`
API index (690 pages): `https://docs.getbifrost.ai/_llms/api.txt`
Repo (default branch `dev`): `https://github.com/maximhq/bifrost`
Schema: `https://www.getmaxim.ai/schema`
Changelogs: `https://docs.getbifrost.ai/changelogs/`
Discord: `https://discord.gg/exN5KAydbU`

> Pin the Bifrost version (`<TAG>`) before copying any snippet — hooks,
> Code Mode, and key-rotation behavior differ between v1.4/v1.5/v2.x.
> When a doc URL 404s, re-discover via `llms.txt` (paths move fast).

## Setup and configuration

| Topic | URL |
|---|---|
| Gateway setup (npx/Docker, flags, app-dir, setup token) | `https://docs.getbifrost.ai/quickstart/gateway/setting-up.md` |
| Dashboard auth (setup token, password) | `https://docs.getbifrost.ai/quickstart/gateway/setting-up-auth.md` |
| Provider configuration | `https://docs.getbifrost.ai/quickstart/gateway/provider-configuration.md` |
| Supported providers overview | `https://docs.getbifrost.ai/providers/supported-providers/overview.md` |
| Provider routing / default resolution | `https://docs.getbifrost.ai/providers/provider-routing.md` |
| config.json quickstart | `https://docs.getbifrost.ai/deployment-guides/config-json.md` |
| Source of truth / reconciliation | `https://docs.getbifrost.ai/deployment-guides/config-json/source-of-truth.md` |
| Schema reference | `https://docs.getbifrost.ai/deployment-guides/config-json/schema-reference.md` |
| Client config | `https://docs.getbifrost.ai/deployment-guides/config-json/client.md` |
| Provider setup in config.json | `https://docs.getbifrost.ai/deployment-guides/config-json/providers.md` |
| Storage (config/logs/vector/object) | `https://docs.getbifrost.ai/deployment-guides/config-json/storage.md` |
| Secret management (env + vault refs) | `https://docs.getbifrost.ai/deployment-guides/config-json/secret-management.md` |
| Governance in config.json | `https://docs.getbifrost.ai/deployment-guides/config-json/governance.md` |
| Plugins in config.json | `https://docs.getbifrost.ai/deployment-guides/config-json/plugins.md` |

## Deployment

| Topic | URL |
|---|---|
| Deploy overview / support matrix | `https://docs.getbifrost.ai/deployment-guides/overview.md` |
| Runtime contract (ports, health, metrics, upgrade) | `https://docs.getbifrost.ai/deployment-guides/runtime-contract.md` |
| Helm quickstart | `https://docs.getbifrost.ai/deployment-guides/helm.md` |
| Helm values reference | `https://docs.getbifrost.ai/deployment-guides/helm/values.md` |
| Helm storage (SQLite/Postgres, StatefulSet migration) | `https://docs.getbifrost.ai/deployment-guides/helm/storage.md` |
| Helm client/providers/governance/plugins | `https://docs.getbifrost.ai/deployment-guides/helm/client.md`, `providers.md`, `governance.md`, `plugins.md`, `secret-management.md`, `cluster.md`, `alerting.md`, `guardrails.md` |
| Helm troubleshooting | `https://docs.getbifrost.ai/deployment-guides/helm/troubleshooting.md` |
| Terraform + k8s | `https://docs.getbifrost.ai/deployment-guides/k8s.md` |
| EKS / GKE / AKS | `https://docs.getbifrost.ai/deployment-guides/platforms/eks.md`, `gke.md`, `aks.md` |
| ECS / fly.io / Cloud Run / Render / Railway | `https://docs.getbifrost.ai/deployment-guides/ecs.md`, `fly.md`, `platforms/cloud-run.md`, `platforms/render.md`, `platforms/railway.md` |
| Nginx reverse proxy (streaming-safe) | `https://docs.getbifrost.ai/deployment-guides/how-to/nginx-reverse-proxy.md` |
| Security best practices (public hosting) | `https://docs.getbifrost.ai/deployment-guides/how-to/security-best-practices.md` |
| Multinode OSS | `https://docs.getbifrost.ai/deployment-guides/how-to/multinode.md` |
| Air-gapped | `https://docs.getbifrost.ai/deployment-guides/how-to/airgapped.md` |
| Docker tuning | `https://docs.getbifrost.ai/deployment-guides/docker-tuning.md` |
| Repo deploy files | `transports/Dockerfile`, `examples/dockers/docker-compose.yml`, `helm-charts/bifrost/`, `terraform/`, `recipes/` |

## Features

| Topic | URL |
|---|---|
| Retries and fallbacks | `https://docs.getbifrost.ai/features/retries-and-fallbacks.md` |
| Keys management | `https://docs.getbifrost.ai/features/keys-management.md` |
| Virtual keys | `https://docs.getbifrost.ai/features/governance/virtual-keys.md` |
| Budgets and limits | `https://docs.getbifrost.ai/features/governance/budget-and-limits.md` |
| Governance routing | `https://docs.getbifrost.ai/features/governance/routing.md` |
| Semantic caching | `https://docs.getbifrost.ai/features/semantic-caching.md` |
| Drop-in replacement | `https://docs.getbifrost.ai/features/drop-in-replacement.md` |
| MCP overview | `https://docs.getbifrost.ai/mcp/overview.md` |
| MCP Code Mode | `https://docs.getbifrost.ai/mcp/code-mode.md` |
| MCP servers / auth / virtual MCPs / filtering | `https://docs.getbifrost.ai/mcp/connecting-to-servers.md`, `gateway-auth.md`, `virtual-mcps.md`, `filtering.md` |
| Observability (default) | `https://docs.getbifrost.ai/features/observability/default.md` |
| Prometheus / OTel / Datadog / Kafka / BigQuery / PubSub / Splunk / Maxim | `https://docs.getbifrost.ai/features/observability/prometheus.md`, `otel.md`, `datadog.md`, `kafka.md`, `bigquery.md`, `pubsub.md`, `splunk.md`, `maxim.md` |
| Vector DBs (redis/weaviate/qdrant/pinecone) | `https://docs.getbifrost.ai/integrations/vector-databases/redis.md` (+ `weaviate.md`, `qdrant.md`, `pinecone.md`) |

## Integrations (drop-in clients)

- OpenAI SDK: `https://docs.getbifrost.ai/integrations/openai-sdk/overview.md`
  (base `http://<HOST>:<PORT>/openai`)
- Anthropic SDK: `https://docs.getbifrost.ai/integrations/anthropic-sdk/overview.md`
  (base `http://<HOST>:<PORT>/anthropic`)
- GenAI SDK: `https://docs.getbifrost.ai/integrations/genai-sdk/overview.md`
  (base `http://<HOST>:<PORT>/genai`)
- Bedrock SDK: `https://docs.getbifrost.ai/integrations/bedrock-sdk/overview.md`
  (base `http://<HOST>:<PORT>/bedrock`)
- LiteLLM / LangChain / PydanticAI / TypeSafe / Passthrough:
  `https://docs.getbifrost.ai/integrations/litellm-sdk.md`,
  `langchain-sdk.md`, `pydanticai-sdk.md`, `typesafe-sdk.md`, `passthrough.md`
- CLI agents (Claude Code, Codex, Gemini, OpenCode, Cursor, Copilot, …):
  `https://docs.getbifrost.ai/cli-agents/overview.md` + per-tool pages
- Runbooks: `https://docs.getbifrost.ai/runbooks/claude-code-bedrock.md`,
  `codex-bedrock.md`

## Develop and modify

| Topic | URL |
|---|---|
| Contributing: setup repo | `https://docs.getbifrost.ai/contributing/setting-up-repo.md` |
| Raising a PR / conventions | `https://docs.getbifrost.ai/contributing/raising-a-pr.md`, `code-conventions.md` |
| Adding a provider / configstore / logstore / vectorstore | `https://docs.getbifrost.ai/contributing/adding-a-provider.md`, `adding-a-configstore.md`, `adding-a-logstore.md`, `adding-a-vectorstore.md` |
| Go SDK setup | `https://docs.getbifrost.ai/quickstart/go-sdk/setting-up.md` |
| Go SDK provider config / context keys | `https://docs.getbifrost.ai/quickstart/go-sdk/provider-configuration.md`, `context-keys.md` |
| Custom plugins (getting started) | `https://docs.getbifrost.ai/plugins/getting-started.md` |
| Writing a Go plugin / dynamic binary / sequencing | `https://docs.getbifrost.ai/plugins/writing-go-plugin.md`, `building-dynamic-binary.md`, `sequencing.md` |
| Core architecture (concurrency/request-flow/MCP/plugins) | `https://docs.getbifrost.ai/architecture/core/concurrency.md`, `request-flow.md`, `mcp.md`, `plugins.md` |
| Framework (what/model-catalog/config-store/log-store/vector-store/streaming) | `https://docs.getbifrost.ai/architecture/framework/what-is-framework.md` (+ `model-catalog.md`, `config-store.md`, `log-store.md`, `vector-store.md`, `streaming.md`) |

## Enterprise (pointers only — not operated by this playbook)

Enterprise overview, moving-from-OSS (sizing, cross-region, hardening,
versioning), user provisioning (OIDC/SCIM: Okta/Entra/Zitadel/Keycloak/
Google/Auth0), clustering, circuit breaker, adaptive routing, guardrails,
alerting, secret managers, log exports, in-VPC:
`https://docs.getbifrost.ai/enterprise/overview.md` and siblings under
`/enterprise/`.
