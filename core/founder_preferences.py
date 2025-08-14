# core/founder_preferences.py
# HAIL — FounderPreferences (Upgraded)
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, asdict, field
from threading import RLock
from typing import Any, Dict, Optional


# Optional sink (best‑effort)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _atomic_write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="prefs_", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as w:
            json.dump(data, w, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


@dataclass
class FounderPrefsModel:
    response_format: str = "structured"       # structured | concise | hybrid
    tone: str = "respectful"                  # respectful | formal | neutral
    language: str = "English"                 # English | Urdu | Arabic
    visuals_enabled: bool = True              # emoji/symbols in UI
    use_system_headers: bool = True           # show module/system labels
    default_greeting: str = "ASSALAM O ALAIKUM!"
    output_order: str = "summary_first"       # summary_first | system_first

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FounderPreferences:
    """
    Persistent founder preferences with validation and thread‑safety.
    Backward‑compatible public methods:
      - get_preference(key)
      - update_preference(key, value) -> bool
      - get_all_preferences() -> dict
      - reset_to_defaults()
    New:
      - save()/reload(), export_json(), import_json()
      - set_mission_log_sink()
    """

    # Allowed values per field (None => free text)
    _SCHEMA = {
        "response_format": {"structured", "concise", "hybrid"},
        "tone": {"respectful", "formal", "neutral"},
        "language": {"English", "Urdu", "Arabic"},
        "visuals_enabled": {True, False},
        "use_system_headers": {True, False},
        "default_greeting": None,  # free text
        "output_order": {"summary_first", "system_first"},
    }

    def __init__(
        self,
        *,
        storage_path: str = "hail/config/founder_preferences.json",
        mission_log_sink: Optional[callable] = None,  # lambda payload: mission_log.append(...)
    ) -> None:
        self._path = storage_path
        self._lock = RLock()
        self._prefs = self._load_or_init()
        self._mission_log_sink = mission_log_sink
        self._action_logger = ActionLogger() if ActionLogger else None

        # ENV overrides (optional, upper‑case keys, e.g., HAIL_PREF_LANGUAGE=Urdu)
        self._apply_env_overrides()

    # ---------- Backward‑compatible API ----------

    def get_preference(self, key: str):
        with self._lock:
            return self._prefs.to_dict().get(key)

    def update_preference(self, key: str, value) -> bool:
        key = str(key)
        if key not in self._SCHEMA:
            return False

        if not self._validate(key, value):
            return False

        with self._lock:
            setattr(self._prefs, key, value)
            self._persist()
            self._sink("PreferenceUpdated", {"key": key, "value": value})
        return True

    def get_all_preferences(self) -> Dict[str, Any]:
        with self._lock:
            return self._prefs.to_dict()

    def reset_to_defaults(self):
        with self._lock:
            self._prefs = FounderPrefsModel()
            self._persist()
            self._sink("PreferencesReset", self._prefs.to_dict())

    # ---------- New helpers ----------

    def save(self) -> None:
        with self._lock:
            self._persist()

    def reload(self) -> None:
        with self._lock:
            self._prefs = self._load_or_init()

    def export_json(self) -> str:
        with self._lock:
            return json.dumps(self._prefs.to_dict(), ensure_ascii=False, indent=2)

    def import_json(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and load a full preferences dict (all or subset)."""
        changed = {}
        with self._lock:
            for k, v in obj.items():
                if k in self._SCHEMA and self._validate(k, v):
                    setattr(self._prefs, k, v)
                    changed[k] = v
            if changed:
                self._persist()
                self._sink("PreferencesImported", changed)
        return changed

    def set_mission_log_sink(self, fn) -> None:
        self._mission_log_sink = fn

    # ---------- Internals ----------

    def _validate(self, key: str, value) -> bool:
        allowed = self._SCHEMA.get(key)
        if allowed is None:
            return True  # free text
        # normalize booleans coming as strings
        if allowed in ({True, False},):
            if isinstance(value, str):
                value = value.strip().lower()
                if value in {"true", "1", "yes", "y"}:
                    value = True
                elif value in {"false", "0", "no", "n"}:
                    value = False
        return value in allowed

    def _load_or_init(self) -> FounderPrefsModel:
        try:
            if os.path.exists(self._path):
                data = json.loads(open(self._path, "r", encoding="utf-8").read())
                return FounderPrefsModel(
                    response_format=data.get("response_format", "structured"),
                    tone=data.get("tone", "respectful"),
                    language=data.get("language", "English"),
                    visuals_enabled=bool(data.get("visuals_enabled", True)),
                    use_system_headers=bool(data.get("use_system_headers", True)),
                    default_greeting=data.get("default_greeting", "ASSALAM O ALAIKUM!"),
                    output_order=data.get("output_order", "summary_first"),
                )
        except Exception:
            # If corrupt, rename and start fresh
            try:
                os.replace(self._path, self._path + ".broken")
            except Exception:
                pass
        # Ensure directory exists and write defaults
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        model = FounderPrefsModel()
        _atomic_write_json(self._path, model.to_dict())
        return model

    def _persist(self) -> None:
        _atomic_write_json(self._path, self._prefs.to_dict())

    def _apply_env_overrides(self) -> None:
        """
        ENV names: HAIL_PREF_RESPONSE_FORMAT, HAIL_PREF_TONE, HAIL_PREF_LANGUAGE,
                   HAIL_PREF_VISUALS_ENABLED, HAIL_PREF_USE_SYSTEM_HEADERS,
                   HAIL_PREF_DEFAULT_GREETING, HAIL_PREF_OUTPUT_ORDER
        """
        env_map = {
            "response_format": os.getenv("HAIL_PREF_RESPONSE_FORMAT"),
            "tone": os.getenv("HAIL_PREF_TONE"),
            "language": os.getenv("HAIL_PREF_LANGUAGE"),
            "visuals_enabled": os.getenv("HAIL_PREF_VISUALS_ENABLED"),
            "use_system_headers": os.getenv("HAIL_PREF_USE_SYSTEM_HEADERS"),
            "default_greeting": os.getenv("HAIL_PREF_DEFAULT_GREETING"),
            "output_order": os.getenv("HAIL_PREF_OUTPUT_ORDER"),
        }
        changed = {}
        with self._lock:
            for k, raw in env_map.items():
                if raw is None:
                    continue
                val = raw
                if k in {"visuals_enabled", "use_system_headers"}:
                    val = raw.strip().lower() in {"1", "true", "yes", "y"}
                if self._validate(k, val):
                    setattr(self._prefs, k, val)
                    changed[k] = val
            if changed:
                self._persist()
                self._sink("PreferencesEnvOverride", changed)

    # ---------- Sinks ----------

    def _sink(self, action: str, payload: Dict[str, Any]) -> None:
        # ActionLogger
        if self._action_logger:
            try:
                self._action_logger.log(
                    action_type=action,
                    user_input="founder_prefs",
                    system_decision="OK",
                    module="founder_preferences",
                    reason=str(payload)[:300],
                    status="Success",
                )
            except Exception:
                pass
        # MissionLog
        if self._mission_log_sink:
            try:
                self._mission_log_sink({
                    "actor_id": "founder",
                    "activity": "preferences_update",
                    "verdict": "halal",
                    "score": 0.05,
                    "reasons": [action],
                    "tags": ["preferences", "founder"],
                    "payload": payload,
                })
            except Exception:
                pass


# ---------------- Example usage ----------------
if __name__ == "__main__":
    fp = FounderPreferences()
    print(fp.get_preference("tone"))  # respectful
    fp.update_preference("tone", "formal")
    print(fp.get_all_preferences())
    # import a batch safely
    print(fp.import_json({"language": "Urdu", "visuals_enabled": "false"}))
    print(fp.export_json())
