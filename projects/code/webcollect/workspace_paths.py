"""Absolute paths for the current single-root workspace."""
from pathlib import Path


def logical(path):
    return str(Path(path).resolve())
