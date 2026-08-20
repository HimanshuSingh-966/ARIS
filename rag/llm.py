"""
rag/llm.py
LLM client — Google AI Studio (Gemini) with a Groq fallback.
Default model: gemini-2.0-flash
"""

import os
import logging

log = logging.getLogger(__name__)

# Substrings that mark a Gemini failure as *transient or capacity-related*, i.e.
# the only cases where silently answering from a different model is defensible.
# Matched against the exception text because google.api_core exception types vary
# across transport backends (grpc vs rest) and versions.
_RETRYABLE_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "quota",
    "rate limit",
    "ratelimit",
    "resource has been exhausted",
    "resource_exhausted",
    "deadline exceeded",
    "unavailable",
    "internal error",
    "overloaded",
    "timeout",
    "timed out",
    "connection",
)


def _is_retryable(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _RETRYABLE_MARKERS)


def generate(messages: list[dict], max_tokens: int = 2048) -> str:
    """
    Send messages to Gemini and return response text.

    Falls back to Groq only for quota / rate-limit / 5xx / network failures.
    Configuration and programming errors (a missing GEMINI_API_KEY, a bad model
    name, a malformed prompt) are re-raised: falling back on those silently
    changed which model answered every single request, so the deployment looked
    healthy while never once using the model it was configured for.

    Args:
        messages   : list of {role, content} dicts
        max_tokens : max response length

    Returns:
        LLM response string
    """
    try:
        import google.generativeai as genai
    except ImportError:
        log.error("google-generativeai not installed — run: pip install google-generativeai")
        raise

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        # Not retryable, and not something Groq should paper over.
        raise RuntimeError("GEMINI_API_KEY is not set in the environment.")

    try:
        genai.configure(api_key=api_key)

        # Use model from env — defaults to gemini-2.0-flash
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        model      = genai.GenerativeModel(
            model_name      = model_name,
            system_instruction = next(
                (m["content"] for m in messages if m["role"] == "system"), None
            )
        )

        # Build conversation history
        history = []
        user_messages = [m for m in messages if m["role"] in ("user", "assistant")]

        for msg in user_messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        # Last message is the current query
        last_msg = user_messages[-1]["content"] if user_messages else ""

        chat     = model.start_chat(history=history)
        response = chat.send_message(
            last_msg,
            generation_config=genai.GenerationConfig(
                max_output_tokens = max_tokens,
                temperature       = 0.1,
            )
        )
        return response.text

    except Exception as e:
        if not _is_retryable(e):
            log.exception("Gemini failed with a non-retryable error — not falling back")
            raise
        log.warning("Gemini unavailable (%s). Falling back to Groq...", e)
        return _generate_groq_fallback(messages, max_tokens)


def _generate_groq_fallback(messages: list[dict], max_tokens: int = 2048) -> str:
    """Fallback to Groq LLM if Gemini hits quota/fails."""
    try:
        from groq import Groq
        groq_api_key = os.environ.get("GROQ_API_KEY")
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY is not set in environment.")

        client = Groq(api_key=groq_api_key)

        # Format messages for Groq API (role must be user, assistant, system)
        groq_messages = []
        for m in messages:
            role = m["role"]
            if role == "model": role = "assistant"
            groq_messages.append({"role": role, "content": m["content"]})

        model_name = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        completion = client.chat.completions.create(
            model=model_name,
            messages=groq_messages,
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return completion.choices[0].message.content or ""
    except ImportError:
        log.error("groq not installed — run: pip install groq")
        raise
    except Exception as e:
        # The message stays internal: api/routes/chat.py logs the trace and
        # answers a generic 502, so no provider detail reaches the client.
        log.error("Groq fallback failed: %s", e)
        raise RuntimeError(f"Both Gemini and Groq failed. Groq error: {e}")
