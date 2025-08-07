# core/device_integrity_scanner.py

import os
import hashlib
import subprocess

class DeviceIntegrityScanner:
    def __init__(self):
        self.baseline_hashes = {}

    def hash_file(self, filepath):
        try:
            with open(filepath, "rb") as f:
                file_data = f.read()
                return hashlib.sha256(file_data).hexdigest()
        except FileNotFoundError:
            return None

    def scan_directory(self, path="./core"):
        results = {}
        for root, _, files in os.walk(path):
            for file in files:
                full_path = os.path.join(root, file)
                hash_val = self.hash_file(full_path)
                results[full_path] = hash_val
        return results

    def set_baseline(self):
        self.baseline_hashes = self.scan_directory()

    def check_for_tampering(self):
        current_hashes = self.scan_directory()
        tampered_files = []

        for path, baseline_hash in self.baseline_hashes.items():
            current_hash = current_hashes.get(path)
            if current_hash != baseline_hash:
                tampered_files.append(path)

        new_files = set(current_hashes.keys()) - set(self.baseline_hashes.keys())
        deleted_files = set(self.baseline_hashes.keys()) - set(current_hashes.keys())

        return {
            "tampered": tampered_files,
            "new": list(new_files),
            "deleted": list(deleted_files)
        }

    def check_running_processes(self):
        try:
            output = subprocess.check_output(["ps", "-A"]).decode("utf-8")
            return output
        except Exception as e:
            return f"Error retrieving processes: {e}"
