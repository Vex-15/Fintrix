# Fintrix — Makefile
# One-command demo & development targets

.PHONY: demo setup test clean help

help: ## Show this help
	@echo "Fintrix — AI Financial Reconciliation"
	@echo ""
	@echo "Targets:"
	@echo "  make demo    — Run the entire pipeline end-to-end"
	@echo "  make setup   — Install all dependencies"
	@echo "  make test    — Run all tests"
	@echo "  make clean   — Remove generated files"
	@echo ""

setup: ## Install backend and frontend dependencies
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

demo: ## Run the entire pipeline and evaluation end-to-end
	python demo.py

test: ## Run all backend tests including determinism
	cd backend && python -m pytest tests/ -v --tb=short

test-determinism: ## Run only the determinism test
	cd backend && python -m pytest tests/test_determinism.py -v

clean: ## Remove generated files
	-del /Q backend\fintrix.db 2>nul
	-del /Q backend\fintrix_demo.db 2>nul
	-del /Q backend\debug_exceptions.txt 2>nul
	-rmdir /S /Q backend\__pycache__ 2>nul
	-rmdir /S /Q backend\.pytest_cache 2>nul
