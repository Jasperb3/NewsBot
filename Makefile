.PHONY: install test run lint

install:
	pip install -e .

test:
	pytest

run:
	newsbot --topics "AI policy, renewable energy" --max-results 6 --out digest.md

lint:
	ruff check newsbot || echo "Install ruff (pip install ruff) to enable linting"
