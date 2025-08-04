# blueprint_auditor.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

class BlueprintAuditor:
    def __init__(self):
        self.phases = {}
        self.required_phases = [f"Phase {i}" for i in range(1, 16)]  # You can extend this based on how many phases exist

    def load_blueprint(self, blueprint_dict):
        """
        blueprint_dict format: {
            "Phase 1": "Verification & Identity Layer",
            "Phase 2": "Memory & Indexing Engine",
            ...
        }
        """
        self.phases = blueprint_dict

    def audit_completeness(self):
        missing = [phase for phase in self.required_phases if phase not in self.phases]
        return {
            "total_required": len(self.required_phases),
            "uploaded": len(self.phases),
            "missing": missing,
            "status": "COMPLETE" if not missing else "INCOMPLETE"
        }

    def check_shariah_keywords(self):
        issues = []
        for phase, content in self.phases.items():
            if "haram" in content.lower() or "unauthorized" in content.lower():
                issues.append((phase, "Potential non-Shari’ah-compliant term found."))
        return issues

    def run_full_audit(self):
        return {
            "completeness_report": self.audit_completeness(),
            "shariah_check": self.check_shariah_keywords()
        }

# Example usage
if __name__ == "__main__":
    bp = BlueprintAuditor()
    test_blueprint = {
        "Phase 1": "Verification & Identity Layer",
        "Phase 2": "Memory & Indexing Engine",
        "Phase 3": "Command Flow & Ethics",
        # ...etc
    }
    bp.load_blueprint(test_blueprint)
    result = bp.run_full_audit()
    print(result)
