"""
rag/llm.py
LLM client — uses Google AI Studio (Gemini).
Default model: gemini-2.0-flash
"""

import os
import logging

log = logging.getLogger(__name__)


def get_provider() -> str:
    return "gemini"


def generate(messages: list[dict], max_tokens: int = 2048) -> str:
    """
    Send messages to Gemini and return response text.

    Args:
        messages   : list of {role, content} dicts
        max_tokens : max response length

    Returns:
        LLM response string
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])

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

    except ImportError:
        log.error("google-generativeai not installed — run: pip install google-generativeai")
        raise
    except Exception as e:
        log.warning(f"Gemini error ({e}). Falling back to Groq...")
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
        log.error(f"Groq fallback failed: {e}")
        raise RuntimeError(f"Both Gemini and Groq failed. Groq error: {str(e)}")