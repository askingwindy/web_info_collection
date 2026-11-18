"""JSON serialization at owned workspace boundaries; standard JSON otherwise."""
import json as _json
from .workspace_paths import encode, decode


def dumps(value,*args,**kwargs):return _json.dumps(encode(value),*args,**kwargs)
def dump(value,stream,*args,**kwargs):return _json.dump(encode(value),stream,*args,**kwargs)
def loads(value,*args,**kwargs):return decode(_json.loads(value,*args,**kwargs))
def load(stream,*args,**kwargs):return decode(_json.load(stream,*args,**kwargs))
def __getattr__(name):return getattr(_json,name)
