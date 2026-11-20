# Copilot repository instructions

- Use Python 3.12 and the stack declared in `pyproject.toml`.
- Keep AI recommendations separate from deterministic risk and execution.
- Never add a live order submission path that can be reached while `PAPER_TRADING=true`.
- Never add a live order path without explicit `LIVE_TRADING_ENABLED=true`, approval/live mode, reconciliation, fresh quotes, and risk checks.
- Never log credentials or unmask `.env` values.
- Use Pydantic validation for external and AI data.
- Add tests for every safety behavior.
