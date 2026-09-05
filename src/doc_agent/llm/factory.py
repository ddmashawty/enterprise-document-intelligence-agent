from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from doc_agent.config import Settings, get_settings


def build_chat_model(settings: Settings | None = None) -> ChatOpenAI:
    s = settings or get_settings()
    if not s.llm_api_key:
        raise RuntimeError("LLM_API_KEY is not configured")
    return ChatOpenAI(
        api_key=s.llm_api_key,
        base_url=s.llm_base_url.rstrip("/"),
        model=s.llm_model,
        temperature=0.2,
        timeout=s.request_timeout,
        max_retries=2,
    )


@lru_cache
def get_chat_model() -> ChatOpenAI:
    return build_chat_model()
