"""Repository-local launcher; installed CLI uses site_planner.__main__."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code'))
from site_planner.__main__ import main

if __name__ == '__main__':
    raise SystemExit(main())
