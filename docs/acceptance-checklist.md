# V1 Acceptance Checklist

Run this checklist on the target host with real AI credentials, a real WeCom robot, and a real phone. Record execution time and evidence for every item. V1 is complete only when every row passes.

| # | Check | Evidence | Status |
|---:|---|---|---|
| 1 | PostgreSQL starts successfully | `docker compose ps`, `pg_isready` healthcheck | Pending target host |
| 2 | Redis starts successfully | `docker compose ps`, `/ready` | Pending target host |
| 3 | Alembic migration succeeds | `docker compose run --rm migrate`, `alembic current` | Pending target host |
| 4 | CNBC RSS collects news | Worker log contains `news_count > 0` | Verified in development; repeat on target |
| 5 | RawNews is persisted | Query `raw_news` | Pending target host |
| 6 | Event is generated | Query `events` | Pending target host |
| 7 | AI Provider call succeeds | Worker log has no auth or HTTP error | Pending real API |
| 8 | Analysis is persisted | Query `news_analyses` and `ai_usages` | Pending real API |
| 9 | Decision Engine works | Inspect Notification status and Timeline | Pending real API |
| 10 | WeCom delivery succeeds | Worker log and WeCom response | Pending webhook |
| 11 | Phone receives a real message | Screenshot and timestamp | Pending webhook |
| 12 | PushDelivery status is correct | Query for `status='sent'` | Pending webhook |
| 13 | Logs contain no unexplained errors | `docker compose logs worker --since 1h` | Pending target host |
| 14 | Services run 24 hours without crash | Uptime, cycle logs, and restart count | Pending target host |

## Suggested database evidence

Run these queries after a successful cycle: `SELECT count(*) FROM raw_news;`, `SELECT count(*) FROM events;`, `SELECT count(*) FROM news_analyses;`, `SELECT count(*) FROM ai_usages;`, `SELECT status, count(*) FROM notifications GROUP BY status;`, `SELECT status, count(*) FROM push_deliveries GROUP BY status;`, and `SELECT action, count(*) FROM notification_timelines GROUP BY action;`.

## Rules

- One failed row means V1 is not formally complete.
- Invalid AI output must appear in `ai_review_queue` and must not create an Analysis.
- Delivery failure must create `PushDelivery.status='failed'` and a failure Timeline.
- A worker/API crash, duplicate delivery, or migration rollback during the 24-hour window resets acceptance.

