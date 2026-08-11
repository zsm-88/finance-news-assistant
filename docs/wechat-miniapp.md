# 微信小程序开发与联调

## 架构边界

小程序仅调用 FastAPI 的 `/api/v1/wechat` 只读接口。数据库访问仍由 Repository 完成，页面和 Service 均不直接使用 SQLAlchemy Session。API 不返回 AI 原始响应、Prompt 快照、Token 明细、密钥、Webhook 或基础设施连接信息。

数据路径为：

```text
PostgreSQL -> Repository -> WeChatReadService -> FastAPI -> 微信小程序
Yahoo Finance -> MarketProvider -> Redis 短缓存 -> MarketService -> FastAPI -> 微信小程序
```

现有采集、AI、Decision Engine、Notification 和企业微信推送链路不受 M7 改动影响。

## 后端启动

在仓库根目录执行：

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/ready
```

预期 `/ready` 返回 `status=ready`。检查接口：

```powershell
Invoke-RestMethod 'http://localhost:8000/api/v1/wechat/news?page=1&page_size=20'
Invoke-RestMethod 'http://localhost:8000/api/v1/wechat/dashboard'
Invoke-RestMethod 'http://localhost:8000/api/v1/wechat/market'
```

详情接口的 ID 使用新闻列表返回的 `id`。

## 接口说明

### `GET /api/v1/wechat/news`

参数：`page`（默认 1）、`page_size`（默认 20，最大 100）、`importance`（1 到 5）、`category`。结果先按 Event 重要性降序，再按新闻发布时间降序。

### `GET /api/v1/wechat/news/{id}`

返回新闻正文、摘要、Event、最新 AI 分析、结构化 MarketImpact 和相关新闻。不存在时返回 404。

### `GET /api/v1/wechat/events`

参数：`limit`（默认 20，最大 100）。返回最新 Event。

### `GET /api/v1/wechat/dashboard`

返回 5 条重要新闻、5 个最新 Event、后端状态和生成时间。首页另外调用行情列表接口生成精简行情摘要。

### `GET /api/v1/wechat/market`

返回 M8 支持的 12 个真实行情标的。数据经过 Redis 60 秒短缓存；数据源不可用时价格为空。

### `GET /api/v1/wechat/market/{symbol}`

返回单个行情详情。只接受后端白名单中的内部代码。

## 开发者工具

从微信官方页面安装微信开发者工具，然后导入仓库中的 `miniapp` 目录。开发者工具模拟器访问本机 API 时，可使用 `http://localhost:8000` 并在本地设置中暂时关闭合法域名校验。这个开关只用于本地开发，不代表真机或发布环境支持 HTTP。

真机、体验版和正式版需要公网 HTTPS API 域名，并在微信公众平台配置为 `request` 合法域名。详见 `miniapp/README.md`。

## 自动测试

```powershell
python -m pytest tests/test_wechat_api.py -q
python -m pytest -q
python -m ruff check src tests migrations
python -m mypy src
node --test miniapp/tests/pages.test.js
```

小程序 JavaScript 可用 `node --check` 做基础语法验证；页面渲染、TabBar、下拉刷新和上拉加载需要在微信开发者工具中进行手工验收。
