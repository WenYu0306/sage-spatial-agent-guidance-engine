.PHONY: demo test lint

demo: ## 单模块演示：auth 登录/越权/刷新轮换
	uv run python -m platform_core.demo

test:
	uv run pytest tests/ -q

lint:
	uv run ruff check .
