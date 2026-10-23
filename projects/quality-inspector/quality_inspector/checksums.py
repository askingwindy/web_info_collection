"""Complete deterministic SHA256 manifest; manifest itself is excluded, not self-hashed."""
from pathlib import Path
import hashlib,re

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def payload(root):
    root=Path(root)
    return sorted(p for p in root.rglob('*') if p.is_file() and p!=root/'SHA256SUMS')
def render(root):
    root=Path(root)
    return ''.join(f'{digest(p)}  {p.relative_to(root).as_posix()}\n' for p in payload(root))
def write_manifest(root):
    root=Path(root);p=root/'SHA256SUMS'
    with p.open('x',encoding='utf-8') as f:f.write(render(root))
def verify_manifest(root):
    root=Path(root).resolve();manifest=root/'SHA256SUMS';errors=[];entries={}
    try:lines=manifest.read_text(encoding='utf-8').splitlines()
    except (OSError,UnicodeError) as e:return {'pass':False,'errors':[str(e)],'entries':0,'payload_files':len(payload(root))}
    for i,line in enumerate(lines,1):
        if not line.strip():continue
        m=re.fullmatch(r'([0-9a-fA-F]{64}) [ *](.+)',line)
        if not m:errors.append(f'line {i}: invalid SHA256 entry');continue
        h,rel=m.groups();p=root/rel
        if Path(rel).is_absolute() or not p.resolve().is_relative_to(root) or p==manifest:errors.append(f'line {i}: invalid/self/outside path {rel}');continue
        if rel in entries:errors.append('duplicate path '+rel)
        entries[rel]=h.lower()
        if not p.is_file() or p.is_symlink() or digest(p)!=h.lower():errors.append('SHA256SUMS entry mismatch '+rel)
    expected={p.relative_to(root).as_posix() for p in payload(root)}
    for rel in sorted(expected-entries.keys()):errors.append('uncovered payload '+rel)
    for rel in sorted(entries.keys()-expected):errors.append('not a payload file '+rel)
    return {'pass':not errors,'errors':errors,'entries':len(entries),'payload_files':len(expected),'self_excluded':'SHA256SUMS','algorithm':'sha256','byte_reproducible':manifest.read_text(encoding='utf-8')==render(root)}
