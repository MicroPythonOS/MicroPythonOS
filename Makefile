all: help

.PHONY: help
help:  ## List all commands
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9 -_]+:.*?## / {printf "\033[36m%-26s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: lint
lint: ## Check code style by run: "ruff check"
	uv tool run ruff check .

.PHONY: lint-fix
lint-fix: ## Check & fix code style by run: "ruff check --fix"
	uv tool run ruff check --fix .

.PHONY: syntax-tests
syntax-tests: ## Run syntax tests
	./tests/syntax.sh

.PHONY: unittest-tests
unittest-tests: ## Run unit tests (Needs to build MicroPythonOS for unix first)
	./tests/unittest.sh

.PHONY: tests
tests: syntax-tests unittest-tests ## Run all tests (Needs to build MicroPythonOS for unix first)
	@echo "All tests passed!"

.PHONY: build-mpos-unix
build-mpos-unix: ## Build MicroPythonOS for unix
	./scripts/build_mpos.sh unix