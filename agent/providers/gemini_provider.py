import logging
import time
from collections.abc import Iterator

from google import genai
from google.genai import errors, types

from agent.providers.base import LLMProvider
from tools.registry import ToolRegistry

logger = logging.getLogger("jarvis.llm")

RETRY_CODES = {429, 500, 503}  # temporary problems worth retrying
ATTEMPTS_PER_MODEL = 2
MAX_TOOL_STEPS = 5             # hard limit so the tool loop can never run away


class _Unavailable(Exception):
    """Every model failed. Carries the last HTTP status code."""

    def __init__(self, code: int | None) -> None:
        super().__init__(f"Gemini unavailable (code {code})")
        self.code = code


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: str = "",
        thinking_level: str = "minimal",
        tools: ToolRegistry | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("LLM_API_KEY is missing. Check your .env file.")
        self._client = genai.Client(api_key=api_key)
        self._thinking_level = thinking_level
        self._registry = tools
        declarations = tools.declarations() if tools else []
        self._tool_config = (
            [types.Tool(function_declarations=declarations)] if declarations else None
        )
        # Try the main model first, then the fallback (if different).
        self._models = [model]
        if fallback_model and fallback_model != model:
            self._models.append(fallback_model)

    # ---- request building ----------------------------------------------
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
        if self._thinking_level and model.startswith("gemini-3"):
            try:
                extra["thinking_config"] = types.ThinkingConfig(
                    thinking_level=self._thinking_level.upper()
                )
            except Exception as exc:
                logger.warning("Could not set thinking level: %s", exc)
        if self._tool_config:
            extra["tools"] = self._tool_config
        return types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=1024,
            # We run the tool loop ourselves, so the SDK must not do it.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            **extra,
        )

    # ---- one model request, with retry and fallback ------------------------
    def _stream_parts(self, contents: list[types.Content], system: str) -> Iterator[types.Part]:
        last_code: int | None = None
        for model in self._models:
            config = self._config(system, model)
            for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
                started = False
                try:
                    for chunk in self._client.models.generate_content_stream(
                        model=model, contents=contents, config=config
                    ):
                        if not chunk.candidates:
                            continue
                        content = chunk.candidates[0].content
                        if content is None or not content.parts:
                            continue
                        for part in content.parts:
                            started = True
                            yield part
                    return
                except errors.APIError as exc:
                    last_code = getattr(exc, "code", None)
                    logger.error("Gemini %s failed (code %s): %s", model, last_code, exc)
                    if started:
                        return  # part of the answer already went out; don't repeat it
                    if last_code in RETRY_CODES and attempt < ATTEMPTS_PER_MODEL:
                        time.sleep(1.5 * attempt)
                        continue
                    break  # try the next model
                except Exception as exc:  # network down, timeouts, etc.
                    logger.error("Could not reach Gemini (%s): %s", model, exc)
                    if started:
                        return
                    raise _Unavailable(None) from exc
            logger.warning("Switching away from model %s", model)
        raise _Unavailable(last_code)

    # ---- tool execution ----------------------------------------------------
    def _run_tool(self, call: types.FunctionCall) -> types.Part:
        args = dict(call.args or {})
        logger.info("Tool call: %s(%s)", call.name, args)
        result = self._registry.execute(call.name, args)  # type: ignore[union-attr]
        return types.Part(
            function_response=types.FunctionResponse(
                id=getattr(call, "id", None), name=call.name, response=result
            )
        )

    @staticmethod
    def _friendly(code: int | None) -> str:
        if code == 429:
            return "Gemini's quota is used up. Try again in a little while."
        if code == 404:
            return "The model name is wrong. Check LLM_MODEL in .env."
        if code is None:
            return "I can't reach my language service right now."
        return "Gemini is busy right now. Please try again in a moment."

    # ---- public API --------------------------------------------------------
    def generate(self, messages: list[dict[str, str]], system: str = "") -> str:
        return "".join(self.stream(messages, system))

    def stream(self, messages: list[dict[str, str]], system: str = "") -> Iterator[str]:
        contents = self._to_contents(messages)
        ran_tools = False
        try:
            for _step in range(MAX_TOOL_STEPS):
                parts: list[types.Part] = []
                calls: list[types.FunctionCall] = []
                said_something = False

                for part in self._stream_parts(contents, system):
                    parts.append(part)  # keep every part exactly as received
                    if part.function_call:
                        calls.append(part.function_call)
                    elif part.text and not getattr(part, "thought", False):
                        said_something = True
                        yield part.text

                if not calls or self._registry is None:
                    if ran_tools and not said_something:
                        yield "Done."
                    return

                ran_tools = True
                contents.append(types.Content(role="model", parts=parts))
                contents.append(
                    types.Content(role="user", parts=[self._run_tool(c) for c in calls])
                )
            yield " I couldn't finish that. It needed too many steps."
        except _Unavailable as exc:
            yield self._friendly(exc.code)