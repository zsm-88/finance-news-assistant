# 免费公网部署方案

本项目提供以下**完全免费**的部署方案，按推荐优先级排列：

---

## 方案 A：Zeabur（最推荐，中国用户友好）

[Zeabur](https://zeabur.com) 提供免费额度：5GB 存储、自定义域名、HTTPS，对中国用户友好（中文界面、支持 ICP 备案）。

### 部署步骤

1. 注册 [Zeabur](https://zeabur.com) 账号
2. 导入此 GitHub 仓库
3. 配置环境变量（复制 `.env.example` 中所有变量）
4. 选择部署区域（推荐香港或日本）
5. 部署完成后绑定自定义域名
6. 微信小程序后台配置合法域名

### 免费额度注意事项

- 每月 5GB 出站流量（个人使用完全足够）
- 服务休眠策略：免费项目 15 分钟无访问会休眠，再次访问自动唤醒
- 数据库建议使用 Zeabur 内置的 PostgreSQL 和 Redis

---

## 方案 B：Railway

[Railway](https://railway.app) 提供 $5/月赠金，足够运行整个项目栈（API + Worker + PostgreSQL + Redis）。

### 部署步骤

```bash
# 1. 安装 Railway CLI
npm install -g @railway/cli

# 2. 登录
railway login

# 3. 在项目目录初始化
railway init

# 4. 添加 PostgreSQL 和 Redis 插件
railway add postgres
railway add redis

# 5. 配置环境变量
railway env set AI_BASE_URL=https://api.siliconflow.cn/v1
railway env set AI_API_KEY=your_key
# ... 设置所有 .env.example 中的变量

# 6. 部署
railway up
```

### 注意事项

- Railway 使用按量计费，$5 赠金足够跑 1 个 API 实例 + 1 个 Worker + 数据库
- 自动提供 HTTPS 和自定义域名

---

## 方案 C：Cloudflare Tunnel（适合有域名的用户）

完全免费，无需云服务器，但需要自有域名。

### 前提条件

- 一个域名（可在 Namesilo、Cloudflare 等平台购买，约 $9/年）
- 本地或 VPS 可运行 Docker

### 部署步骤

```yaml
# docker-compose.cloudflare.yml
services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel --no-autoupdate run --token YOUR_TUNNEL_TOKEN
    restart: unless-stopped
    network_mode: host
```

1. 在 Cloudflare Dashboard 创建 Tunnel
2. 复制 Tunnel Token
3. 将上述 service 添加到 `docker-compose.yml`
4. 配置 DNS 指向 Tunnel
5. HTTPS 自动由 Cloudflare 处理

### 注意事项

- 需要自有域名
- Cloudflare Tunnel 完全免费，无限流量
- 适合已有域名或愿意购买域名的用户

---

## 方案 D：Oracle Cloud Always Free

[Oracle Cloud](https://cloud.oracle.com) 提供永久免费资源：2 核 ARM CPU + 1GB RAM + 200GB 存储。

### 部署步骤

1. 注册 Oracle Cloud 账号（需信用卡验证，但免费）
2. 开通 Always Free VM（选择 Ubuntu 22.04）
3. 安装 Docker 和 Docker Compose
4. 配置 Nginx 反向代理和 Let's Encrypt HTTPS
5. 部署本项目

### 注意事项

- 注册流程较复杂，可能需要尝试多个区域
- 1GB RAM 对 PostgreSQL + Redis + API 三个服务较为紧张
- 建议去掉 Worker 服务，只在 API 中内联采集周期

---

## 通用部署清单

- [ ] 选择部署平台
- [ ] 配置 PostgreSQL（或使用平台托管数据库）
- [ ] 配置 Redis（或使用平台托管 Redis）
- [ ] 设置所有环境变量（参考 `.env.example`）
- [ ] 配置 HTTPS 证书
- [ ] 部署 Migrate 任务（运行 `alembic upgrade head`）
- [ ] 部署 API 服务
- [ ] 部署 Worker 服务（如果需要定时采集）
- [ ] 验证 API 健康检查：`GET /health` → `{"status": "ok"}`
- [ ] 验证数据库就绪：`GET /ready` → `{"status": "ready"}`
- [ ] 微信小程序配置合法域名
- [ ] 小程序体验版测试 → 正式版上线

---

## 环境变量清单

复制 `.env.example` 并配置以下关键变量：

| 变量 | 必填 | 说明 |
|---|---|---|
| `DATABASE_URL` | ✓ | PostgreSQL 连接字符串 |
| `REDIS_URL` | ✓ | Redis 连接字符串 |
| `AI_BASE_URL` | ✓ | AI API 地址（如 SiliconFlow） |
| `AI_API_KEY` | ✓ | AI API Key |
| `AI_MODEL` | ✓ | AI 模型名称 |
| `WECOM_WEBHOOK_URL` | 推送必填 | 企业微信 Webhook |
| `ENABLE_CRAWLER` | | 开启采集 |
| `ENABLE_AI` | | 开启 AI 分析 |
| `ENABLE_PUSH` | | 开启推送 |
| `TELEGRAM_BOT_TOKEN` | 可选 | Telegram Bot 推送 |
| `TELEGRAM_CHAT_ID` | 可选 | Telegram 聊天 ID |