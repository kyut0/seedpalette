.PHONY: install lint format typecheck test check preview clean

install:  ## Install dependencies and git hooks
	poetry install
	poetry run pre-commit install

lint:
	poetry run ruff check .
	poetry run ruff format --check .

format:
	poetry run ruff check --fix .
	poetry run ruff format .

typecheck:
	poetry run mypy

test:
	poetry run pytest --cov=seedpalette --cov-report=term-missing

check: lint typecheck test  ## Everything CI runs

preview:  ## Preview the example themes
	poetry run seedpalette preview examples/themes.yaml -o seedpalette-preview.html

clean:
	rm -rf dist .pytest_cache .mypy_cache .ruff_cache .coverage seedpalette-preview.html
