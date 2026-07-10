"""Shared script bootstrap: path setup, config loading, corpus discovery."""

from __future__ import annotations

import os
import sys

# Make the project's `basin` package importable when scripts are run directly.
_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)

AUDIO_EXTS = (".wav", ".flac", ".ogg", ".mp3", ".aiff", ".aif", ".m4a")


def load_config(path: str | None = None) -> dict:
    import yaml
    path = path or os.path.join(_PROJECT, "config.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def corpus_paths(folder: str | None = None) -> list:
    folder = folder or os.path.join(_PROJECT, "corpus")
    files = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(AUDIO_EXTS):
            files.append(os.path.join(folder, name))
    return files


def instrument_path() -> str:
    return os.path.join(_PROJECT, "instrument.npz")


def debug_dir() -> str:
    d = os.path.join(_PROJECT, "debug")
    os.makedirs(d, exist_ok=True)
    return d


def project_dir() -> str:
    return _PROJECT
