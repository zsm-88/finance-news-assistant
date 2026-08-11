# M2 ORM 与 Repository

所有持久化模型继承 `app.db.base.Base` 和 `ModelMixin`。`ModelMixin` 统一提供 UUID 主键、带时区的 UTC `created_at`/`updated_at` 和可为空的 `deleted_at` 软删除字段。业务查询必须显式过滤 `deleted_at IS NULL`，不得在 Service 中直接调用 SQLAlchemy Session。

核心模型：`Event`、`NewsItem`、`PromptVersion`、`NewsAnalysis`、`MarketImpact`、`EventTimeline`、`PushDelivery`、`JobRun`、`AIUsage`。所有外键均使用 UUID。

Repository 位于 `app.db.repositories`，负责查询构造、持久化和事务边界内的 flush；Service 只依赖具体 Repository 的方法，不感知 SQLAlchemy 查询表达式。Repository 不负责业务编排、AI 调用或推送。

`event_timelines` 是不可变事件审计流：一行代表一次新闻关联、分析完成、推送、人工操作或状态变化，`payload` 保存结构化上下文，供未来 RAG、历史检索和复盘使用。

`market_impacts` 将影响拆成多行资产结论，每行包含 `asset`、`direction`、`confidence`、`reason` 和 `analysis_id`，避免把多资产影响压缩成一段文本。

Alembic 首个迁移创建全部表、外键、唯一约束、检查约束和索引；迁移使用同步 `psycopg` URL，应用运行时仍使用异步 `asyncpg` URL。验证命令：

```powershell
alembic upgrade head
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

第二次 upgrade 必须无变化，downgrade 后再次 upgrade 必须成功。

