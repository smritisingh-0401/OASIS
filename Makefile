# Thin wrappers; scripts/verify.py is the cross-platform entry point (no make on Windows).
UV ?= uv

.PHONY: verify test run-dev bench smoke

verify:
	$(UV) run python scripts/verify.py

test:
	$(UV) run pytest -q

run-dev:
	OASIS_LLM_BACKEND=fake $(UV) run uvicorn oasis.api.app:create_app --factory --host 127.0.0.1 --port 8000

bench:
	$(UV) run python scripts/db_benchmark.py

smoke:
	$(UV) run python scripts/model_smoke_test.py
