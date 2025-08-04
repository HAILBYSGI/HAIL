# founder_protocol.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

import hashlib

class FounderProtocol:
    def __init__(self, founder_name: str, fingerprint_hash: str, dna_hash: str):
        self.founder_name = founder_name
        self.registered_fingerprint = fingerprint_hash
        self.registered_dna = dna_hash

    def verify_fingerprint(self, provided_fingerprint: str) -> bool:
        return self._hash(provided_fingerprint) == self.registered_fingerprint

    def verify_dna(self, provided_dna: str) -> bool:
        return self._hash(provided_dna) == self.registered_dna

    def is_authorized(self, provided_fingerprint: str, provided_dna: str) -> bool:
        return self.verify_fingerprint(provided_fingerprint) and self.verify_dna(provided_dna)

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

# Example usage:
if __name__ == "__main__":
    protocol = FounderProtocol(
        founder_name="Husnain Ali",
        fingerprint_hash="e3b0c44298fc1c149afbf4c8996fb924...",  # Replace with real hash
        dna_hash="a54d88e06612d820bc3be72877c74f257b561b19..."  # Replace with real hash
    )

    print(protocol.is_authorized("sample_fingerprint", "sample_dna"))
