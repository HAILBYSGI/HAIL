# core/device_integrity_scanner.py
# HAIL — DeviceIntegrityScanner (Upgraded)
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from threading import RLock
from typing import Dict, Iterable, List, Optional, Tuple, Any

# Optional sinks (best‑effort; do not hard‑depend)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


CHUNK = 1024 * 1024  # 1MB stream chunks


def _sha256_stream(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                b = f.read(CHUNK)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except (FileNotFoundError, PermissionError, IsADirectoryError):
        return None


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="baseline_", suffix=".json", dir=str(path.parent))
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
class ScanResult:
    root: str
    files: Dict[str, str]  # path -> sha256

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiffReport:
    tampered: List[str]
    new: List[str]
    deleted: List[str]
    unchanged: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeviceIntegrityScanner:
    """
    File integrity scanner for HAIL code and config.
    - Streams SHA‑256 (memory efficient)
    - Include/Exclude glob patterns
    - Baseline save/load with atomic writes
    - Diff report vs baseline
    - Cross‑platform process snapshot (macOS/Linux/Windows)
    """

    DEFAULT_INCLUDE = ["**/*.py", "**/*.json", "**/*.yaml", "**/*.yml", "**/*.txt"]
    DEFAULT_EXCLUDE = [
        ".git/**", "**/__pycache__/**", "**/*.pyc", "hail_logs/**", "hail_data/**",
        ".vscode/**", ".DS_Store", "**/.DS_Store", "venv/**", ".venv/**"
    ]

    def __init__(
        self,
        *,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # lambda payload: mission_log.append(...)
    ) -> None:
        self._baseline: Dict[str, str] = {}
        self._baseline_root: Optional[str] = None
        self._lock = RLock()
        self.log = action_logger
        self.mission_log_sink = mission_log_sink

    # ---------------- Scanning ----------------

    def scan_directory(
        self,
        path: str = "./core",
        include: Optional[Iterable[str]] = None,
        exclude: Optional[Iterable[str]] = None,
    ) -> ScanResult:
        root = Path(path).resolve()
        inc = list(include or self.DEFAULT_INCLUDE)
        exc = list(exclude or self.DEFAULT_EXCLUDE)

        files: Dict[str, str] = {}

        for p in root.rglob("*"):
            rel = p.relative_to(root).as_posix()

            # directories filter (exclude fast)
            if any(fnmatch.fnmatch(rel, pat.rstrip("/")) for pat in exc):
                continue

            # only files that match include
            if p.is_file() and any(fnmatch.fnmatch(rel, pat) for pat in inc):
                digest = _sha256_stream(p)
                if digest is not None:
                    files[str(p)] = digest

        return ScanResult(root=str(root), files=files)

    # ---------------- Baseline ----------------

    def set_baseline(self, path: str = "./core", *, save_to: Optional[str] = "hail_logs/integrity_baseline.json") -> ScanResult:
        sr = self.scan_directory(path)
        with self._lock:
            self._baseline = dict(sr.files)
            self._baseline_root = sr.root
            if save_to:
                _atomic_write_json(Path(save_to), {"root": sr.root, "files": sr.files})
        self._sink_event("BaselineSet", {"files": len(sr.files), "root": sr.root})
        return sr

    def load_baseline(self, from_path: str = "hail_logs/integrity_baseline.json") -> bool:
        p = Path(from_path)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            with self._lock:
                self._baseline = dict(data.get("files", {}))
                self._baseline_root = str(data.get("root"))
            return True
        except Exception:
            return False

    # ---------------- Diffing ----------------

    def check_for_tampering(self, path: Optional[str] = None) -> DiffReport:
        with self._lock:
            baseline = dict(self._baseline)
            if not baseline:
                # No in-memory baseline: try to load default file if exists
                self.load_baseline()

            baseline = dict(self._baseline)
            if not baseline:
                # Still empty → encourage baseline creation
                return DiffReport(tampered=[], new=[], deleted=[], unchanged=0)

            scan_root = path or self._baseline_root or "./core"

        current = self.scan_directory(scan_root).files

        tampered: List[str] = []
        unchanged = 0

        for fpath, base_hash in baseline.items():
            cur = current.get(fpath)
            if cur is None:
                continue  # deletion handled below
            if cur != base_hash:
                tampered.append(fpath)
            else:
                unchanged += 1

        new_files = sorted(set(current.keys()) - set(baseline.keys()))
        deleted_files = sorted(set(baseline.keys()) - set(current.keys()))

        report = DiffReport(
            tampered=sorted(tampered),
            new=new_files,
            deleted=deleted_files,
            unchanged=unchanged,
        )

        # sinks
        if report.tampered or report.deleted:
            self._sink_violation(report)

        return report

    # ---------------- Processes ----------------

    def check_running_processes(self) -> Dict[str, Any]:
        """
        Cross‑platform best effort process snapshot.
        macOS/Linux: `ps -A -o pid,comm`
        Windows: `tasklist`
        """
        try:
            system = platform.system().lower()
            if system in ("darwin", "linux"):
                out = subprocess.check_output(["ps", "-A", "-o", "pid,comm"], text=True, errors="ignore")
                lines = [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]
                procs = []
                for ln in lines:
                    parts = ln.split(None, 1)
                    if len(parts) == 2:
                        pid, cmd = parts
                        procs.append({"pid": pid, "cmd": cmd})
                return {"ok": True, "count": len(procs), "processes": procs[:300]}
            else:  # Windows
                out = subprocess.check_output(["tasklist"], text=True, errors="ignore")
                lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
                return {"ok": True, "raw": "\n".join(lines[:400])}
        except Exception as e:
            return {"ok": False, "error": repr(e)}

    # ---------------- Helpers / Sinks ----------------

    def _sink_event(self, kind: str, meta: Dict[str, Any]) -> None:
        if ActionLogger:
            try:
                ActionLogger().log(
                    action_type="Integrity",
                    user_input=kind,
                    system_decision="INFO",
                    module="device_integrity_scanner",
                    reason=f"{kind}: {meta}",
                    status="Success",
                )
            except Exception:
                pass

    def _sink_violation(self, report: DiffReport) -> None:
        # ActionLogger
        if ActionLogger:
            try:
                ActionLogger().log(
                    action_type="Integrity",
                    user_input="tamper_check",
                    system_decision="DENIED",
                    module="device_integrity_scanner",
                    reason=f"tampered={len(report.tampered)} deleted={len(report.deleted)}",
                    status="CRITICAL" if (report.tampered or report.deleted) else "OK",
                )
            except Exception:
                pass

        # Mission log (optional)
        if self.mission_log_sink:
            try:
                has_issue = bool(report.tampered or report.deleted)
                self.mission_log_sink({
                    "actor_id": "system:integrity",
                    "activity": "integrity_scan",
                    "verdict": "haram" if has_issue else "halal",
                    "score": 0.85 if has_issue else 0.05,
                    "reasons": [
                        f"tampered={len(report.tampered)}",
                        f"deleted={len(report.deleted)}",
                        f"new={len(report.new)}",
                    ],
                    "tags": ["integrity", "security"],
                    "payload": report.to_dict(),
                })
            except Exception:
                pass


# ----------------- Minimal self-test -----------------
if __name__ == "__main__":
    s = DeviceIntegrityScanner()
    # 1) Create baseline for ./core (adjust if needed)
    base = s.set_baseline("./core", save_to="hail_logs/integrity_baseline.json")
    print(f"Baseline files: {len(base.files)}")

    # 2) Re-scan and diff
    rep = s.check_for_tampering()
    print(json.dumps(rep.to_dict(), indent=2))
    # 3) Process snapshot
    print(json.dumps(s.check_running_processes(), indent=2)[:1200])
