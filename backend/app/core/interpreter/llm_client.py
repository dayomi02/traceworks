import json
import logging
from functools import lru_cache

from openai import AsyncOpenAI, OpenAIError

from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def complete(system: str, user: str, model: str | None = None) -> str:
    settings = get_settings()
    _model = model or settings.OPENAI_MODEL
    client = get_client()
    logger.debug("LLM call [complete] model=%s\n--- system ---\n%s\n--- user ---\n%s", _model, system, user)
    try:
        response = await client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except OpenAIError as exc:
        raise LLMUnavailable(str(exc)) from exc
    result = response.choices[0].message.content or ""
    logger.debug("LLM response [complete] model=%s\n%s", _model, result)
    return result


async def complete_json(
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict:
    settings = get_settings()
    _model = model or settings.OPENAI_MODEL
    client = get_client()
    logger.debug("LLM call [complete_json] model=%s\n--- system ---\n%s\n--- user ---\n%s", _model, system, user)
    kwargs: dict = {
        "model": _model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    try:
        response = await client.chat.completions.create(**kwargs)
    except OpenAIError as exc:
        raise LLMUnavailable(str(exc)) from exc
    raw = response.choices[0].message.content or "{}"
    finish_reason = response.choices[0].finish_reason
    if finish_reason == "length":
        logger.warning("LLM response truncated (finish_reason=length). JSON may be incomplete.")
    logger.debug("LLM response [complete_json] model=%s finish=%s\n%s", _model, finish_reason, raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable(f"invalid JSON from LLM: {exc}") from exc
