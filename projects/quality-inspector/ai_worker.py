"""Repository-local independent QC worker launcher."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code'))
from quality_inspector.ai_worker import main

if __name__ == '__main__':
    raise SystemExit(main())
