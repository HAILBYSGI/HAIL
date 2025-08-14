# core/model_bridge.py
import os
from typing import List, Dict, Tuple

def _local_reply(messages: List[Dict[str, str]]) -> str:
    # dead-simple fallback so your app works without API keys
    user = next((m["content"] for m in reversed(messages) if m["role"]=="user"), "")
    if any(w in user.lower() for w in ["haram", "riba", "nudity", "gambling"]):
        return "That seems impermissible. Please avoid and consult a scholar if needed."
    return "Here’s a helpful, concise answer based on your question. (Local demo mode)"

def text_chat(messages: List[Dict[str, str]]) -> Tuple[str, str]:
    """
    Returns (answer, provider_name)
    Provider switches with env:
      HAIL_MODEL_PROVIDER = 'openai' | 'local'
      HAIL_MODEL_NAME = 'gpt-4o-mini' (or any chat-capable model id)
    """
    provider = os.getenv("HAIL_MODEL_PROVIDER", "local").lower()
    if provider != "openai":
        return _local_reply(messages), "local"

    import openai  # pip install openai
    openai.api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("HAIL_MODEL_NAME", "gpt-4o-mini")

    try:
        resp = openai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
        )
        answer = resp.choices[0].message.content.strip()
        return answer, "openai"
    except Exception as e:
        # graceful fallback
        return f"(OpenAI error: {e})\n{_local_reply(messages)}", "openai(fallback)"
