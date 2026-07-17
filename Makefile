-include .env
export

# Install pre-commit hooks
.PHONY: pre_commit_setup
pre_commit_setup:
	uv run pre-commit install

.PHONY: pre_commit_remove
pre_commit_remove:
	uv run pre-commit uninstall

.PHONY: pre_commit_upgrade
pre_commit_upgrade:
	uv run pre-commit autoupdate

.PHONY: install
install:
	uv sync --locked

# Install python dependencies and pre-commit hooks
.PHONY: setup
setup: install pre_commit_setup

# Run pre-commit
.PHONY: pre_commit
pre_commit:
	uv run pre-commit run -a

.PHONY: build
build:
	docker buildx build --platform linux/amd64 -t agents-docintel-api .

.PHONY: all
all:
	uv run app.py

.PHONY: test
test:
	uv run pytest

.PHONY: clean
clean:
