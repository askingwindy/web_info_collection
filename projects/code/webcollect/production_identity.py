"""Optional page ownership and action bounds for the shared collection path.

These mechanical gates do not grant semantic or visual approval. The new
identity binds original page evidence; it does not require an earlier execution
or semantic admission. Collection saves pending evidence for independent QC.
Legacy tasks and numbering remain unchanged.
"""
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from .batch_core import file_sha, load_json
from .planning import canonical, object_sha256, verify_evidence

VERSION = 'webcollect-pilot-page-identity-1'
REVIEW_CHECKS = ('application_identity', 'task_page_identity', 'page_history', 'effective_action_limit')
POLICY_KEY = 'pilot_identity_required'


def _require(value, reason):
    if not value:
        raise ValueError('PILOT_IDENTITY: ' + reason)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def page_url(uri):
    """Conservative URI alias: parameters/fragments cannot create extra pages.

    Query-addressed distinct content remains unsupported by this first pilot
    gate. Such capacity must stay pending rather than weaken the uniqueness.
    """
    _require(_text(uri) and not any(ch.isspace() for ch in uri), 'nonempty public page URI without whitespace required')
    parsed = urlsplit(uri)
    _require(parsed.scheme in ('http', 'https') and parsed.hostname
             and not parsed.username and not parsed.password, 'HTTP(S) URI without credentials required')
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError('PILOT_IDENTITY: invalid URI port') from error
    host = parsed.hostname.lower().rstrip('.')
    port = '' if port is None or port in (80, 443) else ':' + str(port)
    # Scheme/default-port, trailing slash and parameter variants cannot split
    # page ownership. Do not decode encoded slashes or invent redirect aliases.
    path = parsed.path.rstrip('/') or '/'
    return '//' + host + port + path


def _normalized(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    value = re.sub(r'https?://\S+', '<uri>', value)
    value = re.sub(r'\d+(?:\.\d+)?', '<number>', value)
    return re.sub(r'\s+', '', value)


def state_key(state, kind):
    """A second, evidence-derived collision route, never a visual verdict."""
    controls = sorted({(str(row.get('native_role', row.get('element_type', ''))),
                        _normalized(row.get('text', '')))
                       for row in state.get('elements', []) if row.get('visible') is True
                       and (row.get('inputable') or row.get('native_role') in ('input', 'button', 'select', 'textarea'))})
    body = {'title': _normalized(state.get('title', '')), 'controls': controls, 'kind': kind}
    if kind == 'content':
        body['visible_content'] = _normalized(state.get('visible_text', ''))
    return object_sha256(body)


def validate_identity(task, *, observed_states=None):
    value = task.get('pilot_identity')
    if value is None:
        return None
    _require(isinstance(value, dict) and set(value) == {'version', 'application', 'task_page', 'shared_pages'}
             and value['version'] == VERSION, 'unsupported pilot identity binding')
    app, page, shared = value['application'], value['task_page'], value['shared_pages']
    _require(isinstance(app, dict) and {'canonical_uri', 'name', 'evidence'} <= set(app)
             and not set(app) - {'canonical_uri', 'name', 'evidence', 'application_registry'}
             and _text(app['name']) and app['name'] == task.get('app_name'), 'whole application name/URI/evidence required')
    app_uri = urlsplit(app['canonical_uri'])
    page_url(app['canonical_uri'])
    _require(app_uri.path in ('', '/') and not app_uri.query and not app_uri.fragment,
             'first pilot supports one whole public host application, not one app per path')
    verify_evidence(app['evidence'])
    _require(bool(app['evidence']), 'application evidence cannot be empty')
    _require(isinstance(page, dict) and set(page) == {'canonical_uri', 'aliases', 'kind', 'description', 'anchor'}
             and page['kind'] in ('content', 'function') and _text(page['description']), 'task page and original anchor required')
    _require(isinstance(page['aliases'], list) and page['aliases'] and len(set(page['aliases'])) == len(page['aliases'])
             and page['canonical_uri'] in page['aliases'], 'declare canonical task page among exact observed aliases')
    aliases = {page_url(uri) for uri in page['aliases']}
    from .application_identity import canonical_key, host_key
    registry = app.get('application_registry')
    whole = canonical_key(app['canonical_uri'], registry)
    _require(whole == host_key(app['canonical_uri']), 'application URI must be the evidence-backed canonical host')
    _require(all(canonical_key(uri, registry) == whole for uri in page['aliases']),
             'task page host needs evidence-backed whole application ownership')
    from .task_admission import _frame
    state, _ = _frame(page['anchor'], task.get('mode', task.get('observed_workflow', {}).get('mode', 'real')))
    _require(page_url(state.get('url')) in aliases, 'task page anchor does not show a declared page')
    _require(isinstance(shared, list), 'shared pages must be an explicit list')
    shared_urls = set()
    for row in shared:
        _require(isinstance(row, dict) and set(row) == {'uri', 'role', 'reason', 'evidence'}
                 and row['role'] in ('entry', 'intermediate') and _text(row['reason']) and row['evidence'],
                 'shared page exclusion needs role, reason and original evidence')
        verify_evidence(row['evidence'])
        uri = page_url(row['uri'])
        _require(canonical_key(row['uri'], registry) == whole and uri not in aliases
                 and uri not in shared_urls, 'shared page cannot hide a task page or repeat a role')
        shared_urls.add(uri)
    if task.get('initial_url'):
        _require(page_url(task['initial_url']) in aliases | shared_urls, 'starting page has no reviewed role')
    if observed_states is not None:
        from .candidate_contract import same_application
        from .react_session import is_react_task
        # A react session earns its page scope by real same-host navigation;
        # the frozen task cannot list those pages, so the earned set is the
        # observed workflow itself restricted to the evidence-backed
        # application host — exactly the in-session authorization rule.
        earned = ({page_url(row['url']) for row in observed_states
                   if canonical_key(row['url'], registry) == whole}
                  if is_react_task(task) else set())
        _require(observed_states and all((same_application(task,row['url']) if 'candidate_binding' in task else page_url(row['url']) in aliases | shared_urls | earned) for row in observed_states),
                 'actual workflow includes an unbound page')
        from .fragment_workflow import is_fragment
        _require((same_application(task,observed_states[-1]['url']) if 'candidate_binding' in task else page_url(observed_states[-1]['url']) in (aliases | shared_urls | earned if is_fragment(task) or is_react_task(task) else aliases)), 'actual result page cannot be excluded as shared')
        _require(any(page_url(row['url']) in aliases and state_key(row, page['kind']) == state_key(state, page['kind'])
                     for row in observed_states), 'actual task page does not corroborate original content/function anchor')
    return {'binding_sha256': object_sha256(value), 'application_uri': app['canonical_uri'],
            'application_key': page_url(app['canonical_uri']), 'task_page_urls': sorted(aliases),
            'shared_page_urls': sorted(shared_urls), 'content_key': state_key(state, page['kind'])}


def require_actions(task, count, *, final=False, required=False):
    if task.get('pilot_identity') is None and not required:
        return
    from .react_session import is_react_task
    if is_react_task(task):
        # The react protocol has no product step cap: delivery length is
        # judged at derivation and QC (>=5 effective or a documented short
        # flow). Only actually executed actions reach a final proof.
        if type(count) is not int or (final and count < 1):
            raise ValueError('REACT_EXECUTION_BOUNDS: react final proof requires at least one real action')
        return
    if type(count) is not int or count > 10 or final and count < 5:
        raise ValueError('COLLECTION_ACTION_BOUNDS: collection requires 5-10 actual necessary operations; wait/complete do not count')


def before_action(task, raw_records, action_type):
    """Run after automatic preparation chooses the actual next operation."""
    count = sum(bool(row.get('ended_at')) and not row.get('execution_error')
                and row.get('operation', {}).get('action_type') not in ('wait', 'complete')
                for row in raw_records)
    if action_type not in ('wait', 'complete'):
        count += 1
    require_actions(task, count, final=action_type == 'complete', required=True)


def state_allowed(task, state):
    if task.get('pilot_identity') is None:
        return
    binding = validate_identity(task)
    if 'candidate_binding' in task:
        from .candidate_contract import same_application
        _require(same_application(task,state['url']), 'candidate left application')
        return  # Exact action/source navigation is checked by controller and terminal audit.
    _require(page_url(state.get('url')) in set(binding['task_page_urls'] + binding['shared_page_urls']),
             'actual page has no independently reviewed task/shared role')


def actual_proof(task, raw_records, *, final_state=None):
    if task.get('pilot_identity') is None:
        return None
    rows = [row for row in raw_records if row.get('ended_at') and not row.get('execution_error')]
    actions = [row for row in rows if row.get('operation', {}).get('action_type') not in ('wait', 'complete')]
    require_actions(task, len(actions), final=True)
    states = [row['state'] for row in rows]
    if final_state is not None:
        states.append(final_state)
    if 'candidate_binding' in task:
        from .candidate_navigation import verify_path
        verify_path(task,states,[row['operation'] for row in rows])
    identity = validate_identity(task, observed_states=states)
    return {'version': VERSION, **identity, 'effective_actions': len(actions),
            'preparation_actions': sum(row.get('operation_origin') == 'preparation' for row in actions),
            'observed_urls': sorted({row['url'] for row in states}), 'semantic_status': 'REVIEW_REQUIRED'}


def validate_plan(plan, *, required=False):
    tasks = plan.get('tasks', [])
    pilot = [task for task in tasks if task.get('pilot_identity') is not None]
    _require(not required or len(pilot) == len(tasks) > 0, 'campaign requires identity on every new pilot task')
    if pilot:
        _require(plan.get('schema_version') == 'webcollect-plan-m4-1' and len(pilot) == len(tasks),
                 'pilot requires homogeneous strict M4 plans; no legacy direct allocation')
        urls, contents = set(), set()
        for task in pilot:
            binding = validate_identity(task)
            from .agent_controller import is_controlled
            from .react_session import is_react_task
            if not is_controlled(task) and not is_react_task(task):
                require_actions(task, sum(op.get('action_type') not in ('wait', 'complete') for op in task['operations']), final=True)
            from .fragment_workflow import is_fragment, logical_key
            if is_fragment(task):
                key = ('fragment', logical_key(task))
                _require(key not in contents, 'same exact fragment appears twice in plan')
                contents.add(key)
                continue
            _require(not urls.intersection(binding['task_page_urls']), 'same task page appears twice in pilot plan')
            content = (binding['application_key'], binding['content_key'])
            _require(content not in contents, 'same observed content/function appears twice in pilot plan')
            urls.update(binding['task_page_urls']); contents.add(content)
    return bool(pilot)


def ensure_schema(con):
    # Caller owns BEGIN IMMEDIATE. executescript would implicitly commit it.
    con.execute('CREATE TABLE IF NOT EXISTS m4_pilot_page_claims ('
                'claim_key TEXT PRIMARY KEY, task_key TEXT NOT NULL, identity_sha256 TEXT NOT NULL, '
                'application_uri TEXT NOT NULL, accepted_sample_id TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS m4_pilot_applications ('
                'application_key TEXT PRIMARY KEY, canonical_uri TEXT NOT NULL, name TEXT NOT NULL)')


def _keys(binding):
    if binding.get('fragment_key'):
        return ['fragment:' + binding['fragment_key']]
    return ['url:' + uri for uri in binding['task_page_urls']] + [
        'content:' + object_sha256([binding['application_key'], binding['content_key']])]


def react_key(task):
    """Versioned dynamic-execution claim for react tasks.

    Like a fragment key, one claim per frozen boundary+spec; the explicit
    registration version makes a sanctioned re-registration a new transparent
    slot instead of colliding with (or silently reusing) the old one.
    """
    return object_sha256({'url': task['initial_url'], 'boundary': task['fragment'],
                          'spec': task['workflow_proposal']['spec']})


def reserve(con, task_key, task):
    binding = validate_identity(task)
    if binding is None:
        return
    from .fragment_workflow import is_fragment, logical_key
    from .react_session import is_react_task
    if is_react_task(task):
        binding['fragment_key'] = react_key(task)
    elif is_fragment(task):
        binding['fragment_key'] = logical_key(task)
    ensure_schema(con)
    app = task['pilot_identity']['application']
    old_app = con.execute('SELECT canonical_uri,name FROM m4_pilot_applications WHERE application_key=?',
                          (binding['application_key'],)).fetchone()
    _require(not old_app or tuple(old_app) == (binding['application_uri'], app['name']),
             'whole application canonical URI/name changed; preserve original site allocation')
    con.execute('INSERT OR IGNORE INTO m4_pilot_applications VALUES(?,?,?)',
                (binding['application_key'], binding['application_uri'], app['name']))
    for old in con.execute('SELECT task_key,task_json FROM m4_tasks WHERE task_key<>?', (task_key,)):
        prior = json.loads(old['task_json'])
        if not is_fragment(task) and prior.get('pilot_identity') is None and page_url(prior['site_uri']) in binding['task_page_urls']:
            raise ValueError('PILOT_IDENTITY: task page already occurs in original legacy registry; explicit history disposition required')
    for key in _keys(binding):
        old = con.execute('SELECT task_key,identity_sha256 FROM m4_pilot_page_claims WHERE claim_key=?', (key,)).fetchone()
        _require(not old or tuple(old) == (task_key, binding['binding_sha256']), 'real task page already owned by another task/version')
        con.execute('INSERT OR IGNORE INTO m4_pilot_page_claims VALUES(?,?,?,?,NULL)',
                    (key, task_key, binding['binding_sha256'], binding['application_uri']))


def guard(con, task_key, task, *, required=False):
    binding = validate_identity(task)
    _require(binding is not None or not required, 'campaign pilot identity missing before dispatch')
    if binding is None:
        return
    from .fragment_workflow import is_fragment, logical_key
    from .react_session import is_react_task
    if is_react_task(task):
        binding['fragment_key'] = react_key(task)
    elif is_fragment(task):
        binding['fragment_key'] = logical_key(task)
    app = con.execute('SELECT canonical_uri,name FROM m4_pilot_applications WHERE application_key=?',
                      (binding['application_key'],)).fetchone()
    _require(app and tuple(app) == (binding['application_uri'], task['pilot_identity']['application']['name']),
             'original whole application allocation mapping missing or changed')
    for key in _keys(binding):
        row = con.execute('SELECT task_key,identity_sha256,application_uri FROM m4_pilot_page_claims WHERE claim_key=?', (key,)).fetchone()
        _require(row and tuple(row) == (task_key, binding['binding_sha256'], binding['application_uri']),
                 'original atomic page ownership missing or changed')


def allocation_uri(task):
    binding = validate_identity(task)
    return binding['application_uri'] if binding else task['site_uri']


def verify_saved(task, sample_id, evidence):
    if task.get('pilot_identity') is None:
        return
    verify_evidence(evidence)
    candidates = [Path(row['path']) for row in evidence if Path(row['path']).name == 'saved_sample.json']
    _require(len(candidates) == 1, 'pilot success requires original saved-sample receipt')
    receipt = candidates[0]; saved = load_json(receipt)
    _require(saved.get('sample_id') == sample_id and receipt.parent.name == sample_id,
             'pilot saved receipt sample differs')
    sample = receipt.parent.parent.parent / 'samples' / sample_id
    for base, mapping in ((sample, saved.get('sample_files_sha256', {})),
                          (receipt.parent, saved.get('capture_files_sha256', {}))):
        _require(isinstance(mapping, dict) and mapping, 'pilot saved file binding missing')
        for relative, digest in mapping.items():
            path = base / relative
            _require(not Path(relative).is_absolute() and path.resolve().is_relative_to(base.resolve())
                     and not path.is_symlink() and file_sha(path) == digest, 'pilot saved sample/capture bytes changed')
    _require('pilot_identity.json' in saved['capture_files_sha256'], 'pilot actual identity receipt missing')
    raw_paths = sorted(receipt.parent.glob('step_[0-9][0-9][0-9].json'))
    _require('annotation.json' in saved['sample_files_sha256']
             and raw_paths and [path.name for path in raw_paths] ==
                 ['step_' + str(i).zfill(3) + '.json' for i in range(1, len(raw_paths) + 1)]
             and all(path.name in saved['capture_files_sha256'] for path in raw_paths),
             'every consecutive original raw step must be bound by the saved receipt')
    raw = [load_json(path) for path in raw_paths]
    _require(all(row.get('ended_at') and not row.get('execution_error') for row in raw)
             and raw[-1].get('operation', {}).get('action_type') == 'complete'
             and all(row.get('operation', {}).get('action_type') != 'complete' for row in raw[:-1]),
             'saved pilot needs successful original steps and exactly one final complete')
    proof = actual_proof(task, raw)
    record = load_json(receipt.parent / 'pilot_identity.json')
    annotation = load_json(sample / 'annotation.json')
    _require(record == {**proof, 'annotation_sha256': file_sha(sample / 'annotation.json')}
             and annotation.get('sample_id') == sample_id
             and [row['action']['action_type'] for row in annotation['steps']] ==
                 [row['operation']['action_type'] for row in raw]
             and sum(row['action']['action_type'] not in ('wait', 'complete') for row in annotation['steps']) == proof['effective_actions'],
             'actual pilot action/page proof differs from original saved annotation')


def accept(con, task_key, task, sample_id):
    guard(con, task_key, task)
    if task.get('pilot_identity') is None:
        return
    binding = validate_identity(task)
    from .fragment_workflow import is_fragment, logical_key
    if is_fragment(task):
        binding['fragment_key'] = logical_key(task)
    for key in _keys(binding):
        old = con.execute('SELECT accepted_sample_id FROM m4_pilot_page_claims WHERE claim_key=?', (key,)).fetchone()
        _require(old and old[0] in (None, sample_id), 'page already has another accepted effective sample version')
        con.execute('UPDATE m4_pilot_page_claims SET accepted_sample_id=? WHERE claim_key=?', (sample_id, key))
