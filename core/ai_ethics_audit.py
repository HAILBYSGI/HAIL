# core/ai_ethics_audit.py
# Upgraded for HAIL – Qur'an-based AI Ethics & Compliance Tracking
# Founder: Husnain Ali | By the Will & Mercy of Allah (SWT)

from datetime import datetime
from typing import Dict, List, Optional
from core.action_logger import ActionLogger

class AIEthicsAudit:
    """
    Qur’an-governed ethics audit system for HAIL.
    Validates actions against divine rules, logs all checks, 
    and prevents unethical or unverified actions from being executed.
    """

    def __init__(self, log_path: str = "hail_logs/ethics_audit.txt"):
        self.audit_log: List[Dict] = []
        self.violation_count: int = 0
        self.logger = ActionLogger(log_path=log_path)

        # Rules that define the moral boundaries of HAIL
        self.verified_rules: List[str] = [
            "no_shirk", "no_backbiting", "no_falsehood",
            "respect_quran", "preserve_modesty", "founder_alignment",
            "no_haram_content", "no_injustice", "truth_only",
            "protect_ummah", "obey_shariah"
        ]

    def log_action(self, action_type: str, details: str, is_compliant: bool = True, source: str = "system", metadata: Optional[Dict] = None):
        """
        Store an ethics log entry & send it to the action logger for traceability.
        """
        timestamp = datetime.utcnow().isoformat()
        entry = {
            "timestamp": timestamp,
            "action_type": action_type,
            "details": details,
            "compliant": is_compliant,
            "source": source,
            "metadata": metadata or {}
        }

        self.audit_log.append(entry)

        # Save to external log file
        self.logger.log(
            action_type=action_type,
            user_input=metadata.get("user_input", "") if metadata else "",
            system_decision="APPROVED" if is_compliant else "BLOCKED",
            module="ai_ethics_audit",
            reason=details,
            status="Pass" if is_compliant else "Violation"
        )

        if not is_compliant:
            self.violation_count += 1
            print(f"[🚨 ETHICS WARNING] {action_type} violated ethics: {details}")

    def check_against_ethics(self, action_dict: Dict) -> bool:
        """
        Validate the given action against Qur'an-based ethics.
        - action_dict = {
            "type": "response/generation/execution",
            "content": "text or description of action",
            "tags": ["modesty", "truth", "shirk_check", ...],
            "source": "frontend/backend/system",
            "metadata": {...}
        }
        """
        action_tags = action_dict.get("tags", [])
        for tag in action_tags:
            if tag not in self.verified_rules:
                self.log_action(
                    action_type=action_dict.get("type", "unknown"),
                    details=f"Unverified or haram tag detected: {tag}",
                    is_compliant=False,
                    source=action_dict.get("source", "unknown"),
                    metadata=action_dict.get("metadata", {})
                )
                return False

        # Passed all checks
        self.log_action(
            action_type=action_dict.get("type", "unknown"),
            details=action_dict.get("content", ""),
            is_compliant=True,
            source=action_dict.get("source", "unknown"),
            metadata=action_dict.get("metadata", {})
        )
        return True

    def get_audit_summary(self) -> Dict:
        return {
            "total_checks": len(self.audit_log),
            "violations": self.violation_count,
            "last_check": self.audit_log[-1] if self.audit_log else "No actions logged"
        }

    def reset_audit(self):
        self.audit_log.clear()
        self.violation_count = 0
        print("[INFO] Ethics audit log reset.")

# Example test
if __name__ == "__main__":
    ethics = AIEthicsAudit()
    ethics.check_against_ethics({
        "type": "execution",
        "content": "Generate educational material for Islamic studies",
        "tags": ["truth_only", "respect_quran"],
        "source": "frontend",
        "metadata": {"user_input": "Create Islamic course"}
    })
    ethics.check_against_ethics({
        "type": "execution",
        "content": "Display haram images",
        "tags": ["haram_image"],
        "source": "frontend",
        "metadata": {"user_input": "Show non-halal content"}
    })
    print(ethics.get_audit_summary())
