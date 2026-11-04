# SAGE 统一命令入口（US-001）。变量从 .env 读取（-include：文件可不存在）。
-include .env
export

.PHONY: help lint lint-violation-demo test validate gen migrate seed ingest compose-up compose-down

help: ## 列出所有目标
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

TS_FILES := $(shell find packages -type f \( -name '*.js' -o -name '*.ts' -o -name '*.tsx' \) ! -path '*/generated/*' ! -path '*/node_modules/*' 2>/dev/null)

lint: ## ruff + import-linter + eslint（含跨包 import 检查）
	uv run ruff check packages deploy scripts
	uv run lint-imports
	@if [ -n "$(TS_FILES)" ]; then pnpm exec eslint $(TS_FILES); \
	else echo "eslint: 前端暂无 JS/TS 文件，跳过（前端代码落地后自动生效）"; fi

lint-violation-demo: ## 自检：故意造跨包 import（Python+TS 各一），验证 lint 能拦截（拦截=成功）
	@echo "--- Python：import-linter ---"
	@mkdir -p packages/spatial-model/spatial_model packages/content-service/content_service
	@printf '"""故意违规示例：验证 import-linter 契约生效，跑完即删。"""\nimport content_service  # noqa: F401\n' > packages/spatial-model/spatial_model/_violation_demo.py
	@printf '"""故意违规占位。"""\n' > packages/content-service/content_service/__init__.py
	@status=0; uv run lint-imports >/tmp/lint_violation_demo.log 2>&1 || status=$$?; \
	rm packages/spatial-model/spatial_model/_violation_demo.py; \
	cat /tmp/lint_violation_demo.log; \
	if [ $$status -eq 0 ]; then echo "== Python 违规未被拦截，契约失效！=="; exit 1; \
	else echo "== Python 边界拦截成功（退出码 $$status）=="; fi
	@echo "--- TypeScript：eslint-plugin-boundaries ---"
	@mkdir -p packages/admin-web/src packages/screen-web/src
	@printf 'export const x = 1;\n' > packages/screen-web/src/index.js
	@printf 'import { x } from "../../screen-web/src/index.js";\nexport const y = x;\n' > packages/admin-web/src/_violation_demo.js
	@status2=0; pnpm exec eslint packages/admin-web/src/_violation_demo.js >/tmp/eslint_violation_demo.log 2>&1 || status2=$$?; \
	rm -f packages/admin-web/src/_violation_demo.js packages/screen-web/src/index.js; \
	rmdir packages/admin-web/src packages/screen-web/src 2>/dev/null || true; \
	cat /tmp/eslint_violation_demo.log; \
	if [ $$status2 -eq 0 ]; then echo "== TS 违规未被拦截，契约失效！=="; exit 1; \
	else echo "== TS 边界拦截成功（退出码 $$status2）=="; fi

test: ## 全部后端测试 + 前端测试占位
	uv run pytest
	pnpm -r --if-present test

validate: ## 校验 M0 契约（错误码唯一性/分段、JSON Schema 合法性、OpenAPI 骨架）
	uv run --package api-contract python packages/api-contract/scripts/validate.py

gen: ## 从契约 JSON Schema 生成 Pydantic 与 TS 类型
	uv run --package api-contract python packages/api-contract/scripts/gen.py

migrate: ## 跑 Alembic 迁移（deploy/migrations 是唯一改表入口）
	uv run alembic -c deploy/migrations/alembic.ini upgrade head

seed: ## 灌 demo 数据（虚拟商场全量）
	uv run python deploy/seed/seed.py

ingest: ## 知识文档切片+向量化入库（seed 后必须跑，RAG 才有 chunks）
	uv run --package knowledge-rag python -m knowledge_rag.ingest

compose-up: ## 起 postgres + redis
	docker compose up -d
	docker compose ps

compose-down: ## 停并移除容器
	docker compose down
