from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import TypeVar

from pydantic import BaseModel
import httpx

from app.ai import OllamaClient
from app.database import AIReviewCache, get_database


ModelType = TypeVar("ModelType", bound=BaseModel)


class AIInferenceUnavailable(RuntimeError):
    pass


class AIInferenceBudgetExceeded(RuntimeError):
    pass


class AIInferenceCoordinator:
    def __init__(self, env, primary_client: OllamaClient | None = None,
                 lightweight_client: OllamaClient | None = None):
        self.env = env
        self.calls = 0
        self.limit = env.max_ai_calls_per_scan
        self.cache_minutes = env.ai_review_cache_minutes
        self.primary = primary_client or OllamaClient(
            env.ollama_base_url, env.ollama_model, env.ollama_timeout,
            env.ollama_keep_alive, env.ollama_context_size,
            env.ollama_temperature, env.ollama_num_parallel,
        )
        self.lightweight = lightweight_client or OllamaClient(
            env.ollama_base_url, env.ollama_lightweight_model, env.ollama_timeout,
            env.ollama_keep_alive, min(env.ollama_context_size, 2048),
            0, 1,
        )

    def reset_scan(self, max_calls: int | None = None) -> None:
        self.calls = 0
        if max_calls is not None:
            self.limit = max_calls

    def cache_key(self, model_name: str, prompt: str) -> str:
        digest = hashlib.sha256(f"{model_name}\0{prompt}".encode("utf-8")).hexdigest()
        return digest

    def cached(self, key: str) -> dict | None:
        _, session_factory = get_database()
        with session_factory() as session:
            row = session.query(AIReviewCache).filter_by(input_hash=key).first()
            if row is None:
                return None
            if row.expires_at.tzinfo is None:
                expires = row.expires_at.replace(tzinfo=timezone.utc)
            else:
                expires = row.expires_at
            if expires <= datetime.now(timezone.utc):
                session.delete(row)
                session.commit()
                return None
            return dict(row.response)

    def save_cache(self, key: str, model_name: str, response: dict) -> None:
        _, session_factory = get_database()
        expires = datetime.now(timezone.utc) + timedelta(minutes=self.cache_minutes)
        with session_factory() as session:
            row = session.query(AIReviewCache).filter_by(input_hash=key).first()
            if row is None:
                session.add(AIReviewCache(
                    input_hash=key,
                    model_name=model_name,
                    response=response,
                    expires_at=expires,
                ))
            else:
                row.model_name = model_name
                row.response = response
                row.created_at = datetime.now(timezone.utc)
                row.expires_at = expires
            session.commit()

    async def analyze(self, prompt: str, schema: type[ModelType],
                      lightweight: bool = False) -> ModelType:
        if self.calls >= self.limit:
            raise AIInferenceBudgetExceeded(
                f"AI call limit of {self.limit} reached for this scan"
            )
        client = self.lightweight if lightweight else self.primary
        key = self.cache_key(client.model, prompt)
        cached = self.cached(key)
        if cached is not None:
            return schema.model_validate(cached)
        try:
            result = await client.analyze(prompt)
        except (httpx.HTTPError, ConnectionError, TimeoutError, ValueError) as exc:
            raise AIInferenceUnavailable(str(exc)) from exc
        try:
            validated = schema.model_validate(result)
        except Exception as exc:
            raise AIInferenceUnavailable("Ollama response failed Pydantic validation") from exc
        self.calls += 1
        self.save_cache(key, client.model, validated.model_dump())
        return validated
