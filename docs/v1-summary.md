# V1 Project Summary

## Completion status

The implementation and deployment skeleton are complete. Collection, AI Pipeline, notification decision, and WeCom channel code are connected. CNBC RSS was verified with a real HTTP request, and automated checks pass.

Formal V1 completion requires all rows in [acceptance-checklist.md](C:\Users\zhengshumian\Desktop\财经新闻推送\docs\acceptance-checklist.md). The current workspace has no `.env`, PostgreSQL, Redis, AI API key, or WeCom webhook, so real AI invocation, phone receipt, and 24-hour stability are not yet verified. Status: pending target-environment acceptance.

## Implemented

- Docker Compose with PostgreSQL, Redis, migration, API, and worker
- Event/News/RawNews storage and source cursor collection
- CNBC RSS Source Adapter
- Prompt, Context, Provider, Validator, Cache, and Review Queue
- Analysis, MarketImpact, and AIUsage persistence
- Decision Engine, quiet hours, and merge engine
- Notification, NotificationTimeline, and PushDelivery
- WeCom PushChannel implementation
- Unit tests, static checks, type checks, migration checks, and deployment documentation

## Not implemented

- Web administration backend
- Daily or weekly summaries
- RAG and AI question answering
- Portfolio management and position analysis
- Multi-model collaboration
- Proof of 24-hour operation in the target environment

## Known limitations

- CNBC RSS is a public first source; production should use a source with explicit authorization and stable SLA.
- AI cost depends on provider, model, token volume, and collection frequency. `ai_usages` records usage for later accounting.
- A single worker is appropriate for the personal V1 workload, not high-throughput deployment.
- Operations are currently verified through logs and database queries; no Web Dashboard exists.

## Deployment

See [deployment.md](C:\Users\zhengshumian\Desktop\财经新闻推送\docs\deployment.md). The shortest path is: copy `.env.example` to `.env`, fill AI and WeCom required values, then run `docker compose up --build -d`.

## Operations

Back up PostgreSQL regularly. Monitor worker restarts, `ai_review_queue`, failed `push_deliveries`, Redis readiness, and the 24-hour cycle log. Preserve PromptVersion, RawResponse, AIUsage, and NotificationTimeline records for incident review.

## Cost estimate

AI cost is primarily input context tokens plus output summary tokens multiplied by model pricing and collection frequency. A personal low-frequency installation normally fits a small 1-2 vCPU, 2-4 GB RAM cloud host. Main external costs are the cloud host and AI API; WeCom robot messages normally have no separate per-message charge but remain subject to platform limits.

