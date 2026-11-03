# agent-orchestrator 单模块入口（CLAUDE.md 完成定义：make demo 独立跑通）
.PHONY: help demo test lint

help: ## 列出目标
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

demo: ## 单模块演示（兄弟服务 ASGI 内联，无需起端口）
	set -a && . ../../.env && set +a && uv run --package agent-orchestrator python -m agent_orchestrator.demo

test: ## 本模块测试
	uv run --package agent-orchestrator pytest tests -q

lint: ## ruff 本模块
	uv run ruff check .
