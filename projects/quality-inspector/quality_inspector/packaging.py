"""Deprecated QC package compatibility entry; candidate assembly belongs to producer."""
import sys
from pathlib import Path
def build(repo,source,output):
    code=Path(repo)/'projects/code'
    if str(code) not in sys.path:sys.path.insert(0,str(code))
    from webcollect.candidate import build_candidate
    return build_candidate(repo,source,output)
