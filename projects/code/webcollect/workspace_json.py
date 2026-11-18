"""Standard JSON serialization; stored strings are never rewritten."""
import json as _json


dumps = _json.dumps
dump = _json.dump
loads = _json.loads
load = _json.load

def __getattr__(name):
    return getattr(_json, name)
