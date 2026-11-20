from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any
from datetime import datetime, timedelta, timezone
from typing import Literal, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TradeRecommendation(StrictModel):
    ticker: str = Field(min_length=1, max_length=10)
    action: Literal["BUY", "SELL", "HOLD", "WATCH"]
    confidence: float = Field(ge=0, le=1)
    sentiment: str
    investment_thesis: str
    catalysts: list[str] = []
    risks: list[str] = []
    contradictory_evidence: list[str] = []
    supporting_evidence: list[str] = []
    source_references: list[str] = []
    suggested_action: str



class PositionQualityReview(StrictModel):
    ticker: str = Field(min_length=1, max_length=10)
    catalyst_identifiable: bool
    catalyst_fresh: bool
    catalyst_priced_in: bool | None = None
    upside: float = Field(ge=0)
    downside: float = Field(ge=0)
    reward_risk_ratio: float = Field(ge=0)
    decision: Literal["RETAIN", "REDUCE", "CLOSE", "HOLD"]
    thesis: str
    contradictory_evidence: list[str] = []
    source_references: list[str] = []
    confidence: float = Field(ge=0, le=1)


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: int = 300, keep_alive: str = "24h",
                 context_size: int = 4096, temperature: float = 0,
                 num_parallel: int = 1):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.context_size = context_size
        self.temperature = temperature
        self.num_parallel = num_parallel
        self._semaphore = asyncio.Semaphore(1)

    async def analyze(self, prompt: str) -> dict:
        async with self._semaphore:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": self.model,
                          "prompt": "/no_think\n" + prompt,
                          "stream": False,
                          "format": "json",
                          "keep_alive": self.keep_alive,
                          "options": {"num_ctx": self.context_size,
                                      "temperature": self.temperature,
                                      "num_predict": 512,
                                      "num_parallel": self.num_parallel}},
                )
                response.raise_for_status()
                text = response.json()["response"]
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Ollama returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Ollama returned a JSON value instead of an object")
        return parsed

    async def availability(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
            names = {item["name"] for item in response.json().get("models", [])}
            if self.model not in names:
                return False, f"Model {self.model} is not installed"
            return True, "Ollama and model are available"
        except Exception as exc:
            return False, f"Ollama unavailable: {exc.__class__.__name__}"


class PromptManager:
    ALLOWED_VARIABLES = {"ticker", "current_price", "rsi", "macd", "risk_profile",
                         "max_position_percent", "investment_timeframe",
                         "structured_evidence", "symbol", "catalyst_window"}

    def __init__(self, prompt_dir: Path | None = None):
        self.prompt_dir = prompt_dir or Path(__file__).resolve().parent.parent / "prompts"

    def render(self, relative_path: str, variables: dict) -> str:
        path = self.prompt_dir / relative_path
        if not path.is_file():
            raise FileNotFoundError(f"Prompt not found: {relative_path}")
        text = path.read_text(encoding="utf-8")
        import re
        found = set(re.findall(r"\{\{(\w+)\}\}", text))
        unknown = found - self.ALLOWED_VARIABLES
        missing = found - set(variables)
        if unknown:
            raise ValueError(f"Unknown prompt variables: {sorted(unknown)}")
        if missing:
            raise ValueError(f"Missing prompt variables: {sorted(missing)}")
        for key, value in variables.items():
            text = text.replace("{{" + key + "}}", str(value))
        return text
