.PHONY: demo test lint

demo: ## 单模块演示：真库候选打分展示
	uv run python -m recommender.demo

test:
	uv run pytest tests/ -q

lint:
	uv run ruff check .
