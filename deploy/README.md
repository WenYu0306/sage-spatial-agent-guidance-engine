# M13 deploy — 部署资产

## 拓扑

```
外网 → caddy(宿主, 80/443, 自动HTTPS) sage.westwardecho.com
     → 127.0.0.1:8080 nginx(容器: 静态前端 + /api 分流, SSE 关缓冲)
       ├ /api/v1/agent/    → agent:8941（SSE）
       ├ /api/v1/metrics|events → analytics:8946
       ├ /recommend/       → recommender:8944
       ├ /api/             → content:8945（auth/pois/activities/coupons/users/devices...）
       └ /admin/           → admin-web 静态
compose 内网：postgres(pgvector:pg16) redis:7-alpine + route-engine:8942 knowledge-rag:8943
```

## 文件

- `compose.demo.yml`：服务编排 + 内存限额 + 健康检查；migrate/seed/ingest 为 ops profile 一次性任务
- `docker/Dockerfile.service`：六后端共用多阶段镜像（ARG REGISTRY/UV_INDEX_URL 适配国内源）
- `docker/Dockerfile.admin`：admin-web 构建 → nginx
- `scripts/deploy.sh`：拉码→构建→基础设施→迁移→起服务→健康检查→seed+ingest→输出地址
- `scripts/healthcheck.sh` / `backup.sh`（pg_dump 留 14 天）/ `rollback.sh`（上一版 tag）

## 用法（服务器）

```bash
bash deploy/scripts/deploy.sh          # 首次与更新
bash deploy/scripts/backup.sh          # 建议每日 crontab
```

环境变量在服务器 `~/sage/.env.demo`（不在仓库；变量名与 `.env.example` 一致）。
