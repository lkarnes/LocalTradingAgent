import pytest
from pydantic import ValidationError

from app.ai import (OllamaClient, PromptManager, PositionQualityReview,
                    TradeRecommendation)
from app.ai_coordinator import AIInferenceBudgetExceeded, AIInferenceCoordinator


def test_invalid_ai_action_rejected():
    with pytest.raises(ValueError):
        TradeRecommendation(
            ticker="AAPL",
            action="SHORT",
            confidence=0.8,
            sentiment="positive",
            investment_thesis="test",
            suggested_action="none",
        )


def test_prompt_unknown_variable_rejected(tmp_path):
    prompts = tmp_path
    (prompts / "test.md").write_text("{{unknown}}", encoding="utf-8")
    manager = PromptManager(prompts)
    with pytest.raises(ValueError, match="Unknown prompt"):
        manager.render("test.md", {})


def test_position_quality_rejects_extra_fields():
    with pytest.raises(ValidationError):
        PositionQualityReview(
            ticker="AAPL",
            catalyst_identifiable=True,
            catalyst_fresh=True,
            catalyst_priced_in=False,
            upside=10,
            downside=5,
            reward_risk_ratio=2,
            decision="HOLD",
            thesis="test",
            confidence=0.8,
            unexpected="not allowed",
        )


@pytest.mark.asyncio
async def test_ai_call_budget_is_enforced():
    class Env:
        max_ai_calls_per_scan = 1
        ai_review_cache_minutes = 30
        ollama_base_url = "http://127.0.0.1:11434"
        ollama_model = "qwen3:4b"
        ollama_lightweight_model = "qwen3:1.7b"
        ollama_timeout = 1
        ollama_keep_alive = "24h"
        ollama_context_size = 2048
        ollama_temperature = 0
        ollama_num_parallel = 1

    coordinator = AIInferenceCoordinator(Env())
    with pytest.raises(AIInferenceBudgetExceeded):
        coordinator.calls = 1
        await coordinator.analyze("test", TradeRecommendation)
