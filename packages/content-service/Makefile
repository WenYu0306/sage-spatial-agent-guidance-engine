.PHONY: demo test lint

demo: ## 单模块演示：登录/POI 状态机/领券幂等
	uv run python -m content_service.demo

test:
	uv run pytest tests/ -q

lint:
	uv run ruff check .
