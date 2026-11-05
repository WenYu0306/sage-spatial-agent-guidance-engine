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

> **P1 演练（2026-11-06）后须知**：
> 1. 手动执行任何 `docker compose -f deploy/compose.demo.yml ...` 命令时必须带
>    `SAGE_TAG=<git-sha>`——缺省会回落 `latest` 旧镜像（deploy.sh 始终自动导出，不受影响）。
> 2. `SAGE_HTTP`（compose 端口映射，默认 127.0.0.1:8080）与 `SAGE_HTTP_PORT`（healthcheck 探测口）
>    可覆盖宿主端口。
> 3. 服务器 `.env.demo` 变量名以 `platform_core/llm.py` 实际读取为准
>    （`LLM_CHAT_MODEL`/`EMBEDDING_MODEL`/`EMBED_DIM`），模板曾经写错为 `LLM_MODEL`。
