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

.PHONY: check-app-versions
check-app-versions: ## check-app-versions (ARGS='--changed') — apps changed without a MANIFEST bump
	./scripts/check_app_versions.py $(ARGS)

.PHONY: unittest-tests
unittest-tests: ## Run unit tests (Needs to build MicroPythonOS for unix first)
	./scripts/test_runner.py

.PHONY: tests
tests: syntax-tests unittest-tests ## Run all tests (Needs to build MicroPythonOS for unix first)
	@echo "All tests passed!"

.PHONY: build-mpos-unix
build-mpos-unix: ## Build MicroPythonOS for unix
	./scripts/build_mpos.sh unix

.PHONY: build-mpos-unix-coverage
build-mpos-unix-coverage: ## Build MicroPythonOS for unix with sys.settrace coverage support
	./scripts/build_mpos.sh unix coverage

.PHONY: usb-host-tests
usb-host-tests: ## Host unit tests for the USB HID C transport (no hardware)
	$(MAKE) -C c_mpos/usb/tests test

.PHONY: ota-validation
ota-validation: ## Run the hardware OTA release gate (ARGS='--port ... --camera ...')
	./scripts/validate_ota_release.py $(ARGS)

.PHONY: ota-validation-server
ota-validation-server: ## Serve local osupdate metadata for the OTA gate (ARGS='--version ... --hardware-id ...')
	./scripts/ota_validation_server.py $(ARGS)

.PHONY: test-d-shell-host
test-d-shell-host: ## Run D-Shell host regressions without hardware
	python3 tests/cpython_d_shell.py
