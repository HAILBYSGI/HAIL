# memory_store.py
import json
import os

MEMORY_FILE = "hail_memory.json"

# Initialize empty memory if not present
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as f:
        json.dump({}, f)

def load_memory():
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get(key):
    memory = load_memory()
    return memory.get(key)

def set(key, value, founder_authenticated=False):
    if not founder_authenticated:
        raise PermissionError("Only verified Founder may modify HAIL memory.")
    memory = load_memory()
    memory[key] = value
    save_memory(memory)

def delete(key, founder_authenticated=False):
    if not founder_authenticated:
        raise PermissionError("Only verified Founder may delete memory.")
    memory = load_memory()
    if key in memory:
        del memory[key]
        save_memory(memory)
