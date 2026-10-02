from agent.providers.base import LLMProvider
from config.settings import settings
from tools.registry import ToolRegistry


def get_llm_provider(tools: ToolRegistry | None = None) -> LLMProvider:
    if settings.llm_provider == "gemini":
        from agent.providers.gemini_provider import GeminiProvider

        return GeminiProvider(
            settings.llm_api_key,
            settings.llm_model,
            settings.llm_fallback_model,
            settings.llm_thinking_level,
            tools,
        )
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")