import logging
import time
from collections.abc import Iterator

from google import genai
from google.genai import errors, types

from agent.providers.base import LLMProvider

logger = logging.getLogger("jarvis.llm")

RETRY_CODES = {429, 500, 503}  # temporary problems worth retrying
ATTEMPTS_PER_MODEL = 2


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: str = "",
        thinking_level: str = "minimal",
    ) -> None:
        if not api_key:
            raise ValueError("LLM_API_KEY is missing. Check your .env file.")
        self._client = genai.Client(api_key=api_key)
        self._thinking_level = thinking_level
        # Try the main model first, then the fallback (if different).
        self._models = [model]
        if fallback_model and fallback_model != model:
            self._models.append(fallback_model)

    @staticmethod
    def _to_contents(messages: list[dict[str, str]]) -> list[types.Content]:
        # Gemini calls the assistant role "model", not "assistant".
        return [
            types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[types.Part.from_text(text=m["content"])],
            )
            for m in messages
        ]

    def _config(self, system: str, model: str) -> types.GenerateContentConfig:
        extra: dict = {}
        # thinking_level is only for Gemini 3.x models.
        if self._thinking_level and model.startswith("gemini-3"):
            try:
                extra["thinking_config"] = types.ThinkingConfig(
                    thinking_level=self._thinking_level.upper()
                )
            except Exception as exc:
                logger.warning("Could not set thinking level: %s", exc)
        return types.GenerateContentConfig(
            system_instruction=system,
            # Thinking tokens can count toward this limit, so keep it generous.
            # The system prompt already asks for short answers.
            max_output_tokens=1024,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            **extra,
        )

    def generate(self, messages: list[dict[str, str]], system: str = "") -> str:
        return "".join(self.stream(messages, system))

    def stream(self, messages: list[dict[str, str]], system: str = "") -> Iterator[str]:
        contents = self._to_contents(messages)
        last_code: int | None = None

        for model in self._models:
            config = self._config(system, model)
            for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
                started = False
                try:
                    for chunk in self._client.models.generate_content_stream(
                        model=model, contents=contents, config=config
                    ):
                        if chunk.text:
                            started = True
                            yield chunk.text
                    return  # finished successfully
                except errors.APIError as exc:
                    last_code = getattr(exc, "code", None)
                    logger.error("Gemini %s failed (code %s): %s", model, last_code, exc)
                    if started:
                        return  # part of the answer was already spoken; don't repeat it
                    if last_code in RETRY_CODES and attempt < ATTEMPTS_PER_MODEL:
                        time.sleep(1.5 * attempt)
                        continue
                    break  # try the next model
                except Exception as exc:  # network down, timeouts, etc.
                    logger.error("Could not reach Gemini (%s): %s", model, exc)
                    yield "I can't reach my language service right now."
                    return
            logger.warning("Switching away from model %s", model)

        if last_code == 429:
            yield "Gemini ka quota khatam ho gaya hai. Thodi der baad try karo."
        elif last_code == 404:
            yield "Model ka naam galat hai. .env me LLM_MODEL check karo."
        else:
            yield "Abhi Gemini busy hai. Thodi der baad dobara try karo."