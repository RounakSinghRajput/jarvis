import logging
import re
import time

from agent.providers import get_llm_provider
from audio.recorder import MicRecorder
from audio.stt import get_stt_provider
from audio.tts import get_tts_provider
from config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jarvis")

SYSTEM_PROMPT = (
    "You are JARVIS, a helpful personal assistant. "
    "Always reply in simple Hindi written in Devanagari script. "
    "Keep answers to one or two short sentences, since they will be spoken aloud. "
    "Do not use markdown, bullet points, or emojis."
)

# A sentence ends at . ! ? or the Hindi danda followed by whitespace.
SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")
MIN_CHUNK_CHARS = 40  # join very short sentences so speech doesn't sound chopped


def main() -> None:
    llm = get_llm_provider()
    tts = get_tts_provider()
    stt = get_stt_provider()
    recorder = MicRecorder(
        silence_threshold=settings.mic_threshold,
        silence_seconds=settings.mic_silence_seconds,
    )
    history: list[dict[str, str]] = []
    logger.info("Using LLM model: %s", settings.llm_model)
    logger.info("JARVIS ready. Enter = bolo (bolne ke baad phir Enter), ya type karo.")

    try:
        while True:
            typed = input("\n[Enter = bolo, ya type karo]: ").strip()
            if typed.lower() in {"quit", "exit"}:
                break

            t_start = time.perf_counter()
            if typed:
                user_text = typed
            else:
                print("Listening... bolo")
                audio = recorder.record()
                t_rec = time.perf_counter()
                user_text = stt.transcribe(audio)
                t_stt = time.perf_counter()
                logger.info(
                    "TIMING record=%.1fs (audio %.1fs) | whisper=%.1fs",
                    t_rec - t_start, len(audio) / 16000, t_stt - t_rec,
                )
                if not user_text:
                    print("Kuch sunai nahi diya, dobara try karo.")
                    continue
                print(f"You said: {user_text}")

            t_llm_start = time.perf_counter()
            history.append({"role": "user", "content": user_text})
            full_reply = ""
            buffer = ""     # text still arriving from the LLM
            pending = ""    # complete sentences waiting to be sent to TTS
            first_token = True
            first_audio = True
            print("JARVIS: ", end="", flush=True)

            for piece in llm.stream(history, system=SYSTEM_PROMPT):
                if first_token:
                    logger.info("TIMING llm first token=%.1fs", time.perf_counter() - t_llm_start)
                    first_token = False
                print(piece, end="", flush=True)
                full_reply += piece
                buffer += piece

                parts = SENTENCE_END.split(buffer)
                for sentence in parts[:-1]:
                    pending += sentence + " "
                    if len(pending) >= MIN_CHUNK_CHARS:
                        if first_audio:
                            logger.info(
                                "TIMING first chunk queued=%.1fs",
                                time.perf_counter() - t_llm_start,
                            )
                            first_audio = False
                        tts.enqueue(pending)
                        pending = ""
                buffer = parts[-1]

            # Send whatever is left, then wait for speech to finish.
            leftover = (pending + buffer).strip()
            if leftover:
                tts.enqueue(leftover)
            print()
            tts.wait()
            history.append({"role": "assistant", "content": full_reply})
    except KeyboardInterrupt:
        pass
    finally:
        tts.stop()


if __name__ == "__main__":
    main()