"""Strategy-2 wired display logs: stderr runtime lines plus per-worker JSONL.

stdout keeps its machine-readable JSON results untouched; runtime lines go to
stderr, one line per event, flushed immediately. Files append under
``<output>/logs/<workerId>/``: ``runtime.jsonl``, ``model-calls.jsonl`` and
``model-debug.jsonl``. A display-log write failure warns once on stderr and
never triggers a resend or changes any business result. Log fields never enter
business identity hashes or model prompts; the sessionId here is display-only
and never replaces the GLM credential session, claim, attempt, task_key,
request dedup or UNKNOWN identities.
"""
from datetime import datetime
from webcollect import workspace_json as json
from pathlib import Path
import sys
import threading
import uuid


LEVELS = ('INFO', 'DEBUG')
IDENTITY_KEYS = ('sessionId', 'strategy', 'template_name', 'workerId', 'siteId',
                 'candidateId', 'claimId', 'attemptId', 'sampleId')
_SENSITIVE_KEYS = frozenset({'authorization', 'cookie', 'api_key', 'api-key', 'token',
                             'password', 'credential', 'credentials', 'reasoning_content'})


def new_session_id():
    return str(uuid.uuid4())


def now_iso():
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


def _terminal(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, str):
        return value if not (' ' in value or '=' in value) else json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def sanitize_debug(value):
    """Drop credentials and reasoning bodies; replace image data URLs with refs.

    Recursively applied to anything written to model-debug.jsonl so no API key,
    Authorization header, Cookie or login state ever reaches the rolling log
    and no large base64 payload is inlined.
    """
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                clean[key] = '<omitted>'
                continue
            clean[key] = sanitize_debug(item)
        return clean
    if isinstance(value, list):
        return [sanitize_debug(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_debug(item) for item in value]
    if isinstance(value, str) and value.startswith('data:image'):
        return '<data-url-omitted:' + str(len(value)) + '>'
    return value


def image_references(images):
    """File reference, sha256, byte size and pixel dimensions per original image."""
    from .batch_core import file_sha
    references = []
    for path in images:
        path = Path(path)
        entry = {'path': str(path.resolve()), 'sha256': file_sha(path),
                 'bytes': path.stat().st_size}
        try:
            from PIL import Image
            with Image.open(path) as image:
                entry['width'], entry['height'] = image.size
        except Exception:
            entry['width'] = entry['height'] = None
        references.append(entry)
    return references


class SessionLog:
    """One consumption session's display-only log context.

    The identity fields are attached once and never enter business state: an
    attemptId or sampleId only supplements the correlation after it is
    allocated; the sessionId itself stays stable from entry observation to
    final close-out.
    """

    def __init__(self, output, worker_id, session_id, strategy=None, *, level='INFO',
                 log_dir=None, site_id=None, candidate_id=None, claim_id=None,
                 attempt_id=None, sample_id=None):
        if level not in LEVELS:
            raise ValueError('log level must be one of ' + '/'.join(LEVELS))
        self.session_id = str(session_id)
        self.worker_id = str(worker_id)
        self.level = level
        root = Path(log_dir) if log_dir is not None else Path(output) / 'logs' / self.worker_id
        self._dir = Path(root)
        self._warned = set()
        self._lock = threading.Lock()
        self._fields = {'sessionId': self.session_id, 'strategy': strategy,
                        'template_name': None,
                        'workerId': self.worker_id, 'siteId': site_id,
                        'candidateId': candidate_id, 'claimId': claim_id,
                        'attemptId': attempt_id, 'sampleId': sample_id}

    @property
    def debug_enabled(self):
        return self.level == 'DEBUG'

    def attach(self, **fields):
        """Supplement correlation fields (attemptId/sampleId); never the sessionId."""
        with self._lock:
            for key, value in fields.items():
                if key in IDENTITY_KEYS and key != 'sessionId':
                    self._fields[key] = value
        return self

    def _identity(self):
        with self._lock:
            return dict(self._fields)

    def _write_failed(self, path):
        if str(path) in self._warned:
            return
        self._warned.add(str(path))
        try:
            print('日志写入失败：展示日志不可用，业务结果不受影响 ' + str(path),
                  file=sys.stderr, flush=True)
        except Exception:
            pass

    def _append(self, name, record):
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            with (self._dir / name).open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                         allow_nan=False, default=str) + '\n')
                stream.flush()
        except OSError:
            self._write_failed(self._dir / name)

    def log(self, level, event, **fields):
        if level not in LEVELS:
            return
        record = {'ts': now_iso(), 'level': level, 'event': event,
                  **self._identity(), **fields}
        with self._lock:
            try:
                line = ' '.join([record['ts'], level]
                                + [key + '=' + _terminal(record.get(key))
                                   for key in IDENTITY_KEYS + ('event',)]
                                + [key + '=' + _terminal(value)
                                   for key, value in fields.items()])
                print(line, file=sys.stderr, flush=True)
            except Exception:
                self._write_failed('<stderr>')
            self._append('runtime.jsonl', record)

    def info(self, event, **fields):
        self.log('INFO', event, **fields)

    def warn(self, event, **fields):
        self.log('INFO', event, severity='warn', **fields)

    def banner(self, site_name):
        self.info('session_start', site=site_name)

    def session_end(self, **fields):
        self.info('session_end', **fields)

    def model_call(self, **fields):
        """One model-calls.jsonl row: per physical request facts only."""
        record = {'ts': now_iso(), **self._identity(), **fields}
        with self._lock:
            self._append('model-calls.jsonl', record)

    def model_debug(self, **fields):
        if not self.debug_enabled:
            return
        record = {'ts': now_iso(), **self._identity(),
                  **{key: sanitize_debug(value) for key, value in fields.items()}}
        with self._lock:
            self._append('model-debug.jsonl', record)


def for_claim(output, worker_id, claim, strategy=None, *, level='INFO', log_dir=None):
    """Claim-based consumption uses the claim_id itself as the display sessionId."""
    return SessionLog(output, worker_id, claim['claim_id'], strategy, level=level,
                      log_dir=log_dir, candidate_id=claim.get('candidate_id'),
                      claim_id=claim.get('claim_id'))


def for_direct_run(output, worker_id=None, strategy=None, *, level='INFO', log_dir=None):
    """A no-claim direct execution generates its sessionId exactly once."""
    import os
    return SessionLog(output, worker_id or ('direct-' + str(os.getpid())),
                       new_session_id(), strategy, level=level, log_dir=log_dir)
