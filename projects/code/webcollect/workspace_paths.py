"""Explicit workspace-root serialization for newly prepared projects only.

Legacy absolute strings retain their representation. No cwd lookup or historical rewrite.
"""
from contextvars import ContextVar
import json
import os
from pathlib import Path

_root=ContextVar('webcollect_workspace_root',default=None)
PREFIX='workspace:/'

class HistoricalAbsolute(str):
    """An absolute string read from an existing original; do not rewrite it."""

class WorkspacePath(str):
    pass


def root_for(path):
    path=Path(path).resolve()
    for folder in (path if path.is_dir() else path.parent, *path.parents):
        marker=folder/'.workspace-root.json'
        if marker.is_file():
            value=json.loads(marker.read_text())
            return (folder/value['workspace_root']).resolve()
    return None


def bind(path):
    root=root_for(path)
    _root.set(root)
    return root


def prepare(folder, root):
    folder,root=Path(folder).resolve(),Path(root).resolve()
    folder.mkdir(parents=True,exist_ok=True)
    marker=folder/'.workspace-root.json'
    data={'workspace_root':os.path.relpath(root,folder)}
    if marker.exists() and json.loads(marker.read_text())!=data:
        raise ValueError('Workspace root binding changed')
    if not marker.exists():marker.write_text(json.dumps(data)+'\n')
    _root.set(root)


PATH_FIELDS = frozenset(('path','ledger','registry','pool','site_ledger','output','history_set',
    'producer_db','consumer_db','producer_config','consumer_config','policy','qc_policy',
    'scope','source_scope','manifest','current_result_roots','result_location','result_locations',
    'image','state_path','capture_path','html_path','api_key_file','source_root','resource_root',
    'result_root','results_root','output_root','evidence_root','log_root','log_dir','raw_root',
    'prepared_path','registry_path','pool_path','model_ledger','catalog','plan_file','sources_path',
    'original_registry','original_ledger','annotation_path','delivery_root','history_registry'))


def encode(value, field=None):
    root=_root.get()
    if isinstance(value,HistoricalAbsolute):return str(value)
    is_path = isinstance(value,WorkspacePath) or field in PATH_FIELDS or bool(isinstance(field,str) and (field.endswith('_path') or field.endswith('_root')))
    if isinstance(value,str) and root and is_path and value.startswith(str(root)+os.sep):
        return PREFIX+Path(value).relative_to(root).as_posix()
    if isinstance(value,dict):return {k:encode(v,k) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [encode(v,field) for v in value]
    return value


def decode(value):
    root=_root.get()
    if isinstance(value,str):
        if value.startswith(PREFIX):
            if root is None:raise ValueError('Relative workspace reference has no explicit owning root')
            relative=Path(value[len(PREFIX):])
            if relative.is_absolute() or '..' in relative.parts:raise ValueError('Workspace reference escapes root')
            return WorkspacePath(str(root/relative))
        if value.startswith('/'):return HistoricalAbsolute(value)
        return value
    if isinstance(value,dict):return {k:decode(v) for k,v in value.items()}
    if isinstance(value,list):return [decode(v) for v in value]
    return value


def logical(path):
    root=root_for(path)
    return (str(Path(path).resolve().relative_to(root)) if root else str(Path(path).resolve()))


def prepare_output(folder, owner):
    """Give a new artifact directory the same explicit root as its owning scope."""
    root=root_for(owner)
    folder=Path(folder).resolve()
    if root and folder.is_relative_to(root):prepare(folder,root)
