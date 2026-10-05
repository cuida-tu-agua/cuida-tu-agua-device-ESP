# Small JSON files in the ESP32 flash (wifi.json, valve.json). They survive restarts and power cuts.
import json
import os


def load(name, default=None):
    try:
        with open(name) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(name, data):
    # Write a temp file and rename it: a power cut in the middle never leaves a half-written file
    tmp = name + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    try:
        os.rename(tmp, name)
    except OSError:
        remove(name)          # FAT does not rename over an existing file
        os.rename(tmp, name)


def remove(name):
    try:
        os.remove(name)
    except OSError:
        pass
