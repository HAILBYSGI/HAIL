# phase_summary_cache.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

import time

class PhaseSummaryCache:
    def __init__(self, expiration_seconds=3600):
        self.cache = {}
        self.expiration = expiration_seconds

    def _current_time(self):
        return time.time()

    def set_summary(self, phase_name, summary_text):
        """
        Stores the summary with a timestamp for expiration tracking.
        """
        self.cache[phase_name] = {
            "summary": summary_text,
            "timestamp": self._current_time()
        }

    def get_summary(self, phase_name):
        """
        Returns cached summary if it hasn’t expired.
        """
        if phase_name in self.cache:
            entry = self.cache[phase_name]
            if self._current_time() - entry["timestamp"] < self.expiration:
                return entry["summary"]
            else:
                del self.cache[phase_name]
        return None

    def clear_cache(self):
        """
        Clears all cached summaries.
        """
        self.cache = {}

# Example usage
if __name__ == "__main__":
    cache = PhaseSummaryCache()
    cache.set_summary("Phase 1", "Phase 1 includes systems for founder verification and core protection.")
    
    print(cache.get_summary("Phase 1"))  # Should return the summary
    time.sleep(2)
    print(cache.get_summary("Phase 1"))  # Still valid
