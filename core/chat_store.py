# core/chat_store.py
import os, json, time
from typing import Dict, Any, List

DATA_PATH = os.path.join("hail_data", "chat_history.json")
os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
if not os.path.exists(DATA_PATH):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump([], f)

def append_message(actor_id: str, role: str, text: str, verdict: str = None, score: float = None):
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        arr: List[Dict[str, Any]] = json.load(f)
    arr.append({
        "ts": time.time(),
        "actor_id": actor_id,
        "role": role,
        "text": text,
        "verdict": verdict,
        "score": score
    })
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(arr, f, ensure_ascii=False, indent=2)

def load_all() -> List[Dict[str, Any]]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
