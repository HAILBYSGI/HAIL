# quran_filter.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

class QuranFilter:
    def __init__(self):
        self.prohibited_keywords = [
            "haram", "shirk", "riba", "nudity", "violence", "falsehood",
            "mocking", "gambling", "intoxicants"
        ]

    def is_halal(self, text: str) -> bool:
        for word in self.prohibited_keywords:
            if word.lower() in text.lower():
                return False
        return True

    def analyze_text(self, text: str):
        issues_found = []
        for word in self.prohibited_keywords:
            if word.lower() in text.lower():
                issues_found.append(word)
        if not issues_found:
            return {"status": "Halal", "issues": []}
        return {"status": "Restricted", "issues": issues_found}

# Example usage
if __name__ == "__main__":
    qf = QuranFilter()
    sample = "This message contains riba and violence."
    result = qf.analyze_text(sample)
    print(result)
