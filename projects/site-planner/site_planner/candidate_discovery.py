"""Lightweight candidate producer: search/source -> one structured AI list -> SQLite.

No browser imports or qualification. Explicit bounded queries; repeated batches use
original search cache, model jobs and immutable checkpoints, including UNKNOWN.

candidate-producer-3 publishes entry/target candidates (webcollect-data-candidate-2)
row by row: the outer response shape is checked once, each row gets its own stable
conclusion, and interrupted batches resume from the original response only.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
import re
import time
import unicodedata
from pathlib import Path
from webcollect.batch_core import BatchLedger, BudgetStop, OutcomeUnknown, load_json, save_json
from webcollect.model_gateway import ModelGateway
from webcollect.planning import object_sha256, verify_evidence
from webcollect.site_failure_stop import SiteStopped
from .candidate_pool import (CandidatePool, VERSION2, validate_target, normalize,
                             validate_candidate_v2)
from .site_pool import SitePool, page_uri, host_identity
from .discovery_tools import glm_search, reference
from .entry_access import POLICY as ENTRY_HTTP_POLICY, check_entry
from .discovery_agent import model_decision, model_tool_decision, SettledSelectionRejected
from .qualification import CANONICAL_CATEGORIES, BUSINESS_CATEGORIES
from . import entry_selection as selection
from .producer_authority import isolation_host
from . import application_discovery as site_tables

# Stable query-policy identity. The literal is historical: frozen batches'
# checkpoints and decision reasons carry exactly this value, so it must stay
# byte-identical for old batches to resume.
QUERY_POLICY = 'producer-query-policy-1'

SCHEMA = {'type':'object','additionalProperties':False,'required':['candidates'], 'properties':{'candidates':{
    'type':'array','maxItems':100,'items':{'type':'object','additionalProperties':False,
    'required':['source_index','name','parent_category','business_kind','description','target'], 'properties':{
    'source_index':{'type':'integer','minimum':0}, 'name':{'type':'string','minLength':1},
    'parent_category':{'enum':list(CANONICAL_CATEGORIES)}, 'business_kind':{'type':'string','minLength':1},
    'description':{'type':'string','minLength':1}, 'target':{'type':'object','additionalProperties':False,
    'required':['kind','entity','parameters'],'properties':{'kind':{'type':'string','minLength':1},
    'entity':{'type':'string','minLength':1},'parameters':{'type':'object'},'flags':{'type':'string'}}}}}}}}


def normalize_candidate(row):
    from copy import deepcopy
    value=deepcopy(row); target=value['target']; rules=[]
    if 'flags' in target:
        flags=target.pop('flags')
        if 'flags' in target['parameters'] and target['parameters']['flags']!=flags:
            raise ValueError('Conflicting flags; preserve original response')
        target['parameters']['flags']=flags
        rules.append('candidate-flat-flags-to-parameters-1')
    return value,rules


def strict_schema(count, source_count):
    schema=deepcopy(SCHEMA);rows=schema['properties']['candidates']
    rows.update(minItems=count,maxItems=count)
    rows['items']['properties']['source_index']['maximum']=source_count-1
    rows['items']['properties']['target']['properties'].pop('flags')
    for key in ('name','business_kind','description'):
        rows['items']['properties'][key]['pattern']=r'\S'
    for key in ('kind','entity'):
        rows['items']['properties']['target']['properties'][key]['pattern']=r'\S'
    return schema


def validate_source_binding(row, hit):
    """Reject explicit foreign app identities; snippets do not transfer ownership.

    This is a conservative structural check, not a general semantic classifier.
    Source-evidence review still checks article/target meaning independently.
    """
    match=re.match(r'^(?:https?://)?((?:[a-zA-Z0-9-]+\.)+(?:com|cn|net|org|io|dev|app|edu|gov))(?=[^a-zA-Z0-9.-]|$)',row['target']['entity'])
    if match and host_identity('https://'+match[1]+'/')!=host_identity(hit['uri']):
        raise ValueError('Target application identity belongs to another host mentioned by the source; do not use an article as that application')


def reference_article_for_tool_query(query, hit):
    """Conservative search-evidence triage, not a page eligibility claim.

    Article content remains a legitimate target for content discovery. Only an
    explicitly interactive tool query avoids these reference-like search hits.
    """
    if re.search(r'阅读|读文章|查阅资料',query) or not re.search(r'在线工具|单位换算|计算器',query):return False
    title=hit.get('title','');content=hit.get('content','')
    return bool(re.search(r'使用指南|操作教程|工具推荐|APP\s*推荐',title)
        or re.search(r'作者\s*\n',content)
        or '/article/details/' in hit['uri'] or '/article/' in hit['uri'])


def _entry_http_binding(previous, config):
    if previous is not None and 'entry_http_policy' not in previous:
        return {}  # Original batches retain their frozen policy and receipts.
    if config['mode']=='real' and not config.get('site_failure_guard'):
        raise ValueError('Real producer entry checks require the original whole-site failure guard')
    return {'entry_http_policy': ENTRY_HTTP_POLICY}


def _save_bound_json(path, value):
    if Path(path).exists():
        if load_json(path) != value:
            raise ValueError('Original tool evidence changed')
    else:
        save_json(path, value)


_LEADING_DOMAIN = re.compile(r'^(?:https?://)?((?:[a-zA-Z0-9-]+\.)+(?:com|cn|net|org|io|dev|app|edu|gov))(?=[^a-zA-Z0-9.-]|$)')


def normalize_query(query):
    return ' '.join(unicodedata.normalize('NFKC', query).split()).casefold()


def read_directions(path):
    directions = load_json(path)
    if isinstance(directions, dict):
        directions = directions.get('directions')
    if not isinstance(directions, list):
        raise ValueError('Expected a directions array or an object with a directions array')
    return directions


def normalize_directions(directions):
    out = []
    for direction in directions:
        if not isinstance(direction, dict) or set(direction) - {'direction', 'category', 'queries', 'target_share'} \
                or not isinstance(direction.get('direction'), str) or not direction['direction'].strip():
            raise ValueError('Each direction needs a name and a bounded query list')
        from .site_pool import category
        category(direction.get('category', 'UNKNOWN'))
        queries = direction['queries']
        if not isinstance(queries, list) or not queries or any(
                not isinstance(q, str) or not 1 <= len(q) <= 70 for q in queries):
            raise ValueError('Each direction needs 1-70 character queries')
        if len({normalize_query(q) for q in queries}) != len(queries):
            raise ValueError('Duplicate queries inside one direction')
        share = direction.get('target_share')
        if share is not None and (not isinstance(share,(int,float)) or isinstance(share,bool) or not 0 < share <= 1):
            raise ValueError('target_share must be in (0,1]')
        out.append({'direction': direction['direction'].strip(),
                    'category': direction.get('category', 'UNKNOWN'), 'queries': list(queries),
                    **({'target_share':share} if share is not None else {})})
    if len({d['direction'] for d in out}) != len(out):
        raise ValueError('Direction names must be unique')
    return out


class QueryPolicy:
    """Deterministic, versioned search-word adjustment over caller terms.

    Rules (producer-query-policy-1), all reproducible from persisted stats:
    1. Explicit caller sources are handled before any search and never block this policy.
    2. Prefer the direction with the fewest completed queries; ties break by seed order.
    3. Within a direction take the next unused query (normalized dedup; blocked
       original-UNKNOWN queries are skipped and never resent). A tool query whose
       hits were mostly articles moves on to the next term.
    4. After ``stall_threshold`` consecutive completed distinct queries with zero
       new entries the direction is deprioritized while any direction with unused
       queries remains.
    5. A direction is exhausted at ``per_direction_cap`` used queries or when its
       terms run out; everything exhausted or stalled ends search with a deficit.
    """

    def __init__(self, directions, *, stall_threshold=2, per_direction_cap=None):
        self.directions = normalize_directions(directions)
        if not 1 <= stall_threshold <= 10 or (per_direction_cap is not None and
                (type(per_direction_cap) is not int or per_direction_cap < 1)):
            raise ValueError('Bounded policy thresholds required')
        self.stall_threshold = stall_threshold
        self.cap = per_direction_cap

    def initial_state(self):
        return {'version': QUERY_POLICY, 'stall_threshold': self.stall_threshold,
                'per_direction_cap': self.cap, 'queries': {}, 'order': [], 'blocked': {}}

    def _entries(self, state):
        per = {}
        for key in state['order']:
            entry = state['queries'][key]
            per.setdefault(entry['direction'], []).append(entry)
        return per

    def _unused(self, direction, state):
        return [q for q in direction['queries']
                if normalize_query(q) not in state['queries'] and normalize_query(q) not in state['blocked']]

    def _stalled(self, entries, threshold):
        zero = 0
        for entry in reversed(entries):
            if entry['new_entries'] > 0:
                break
            zero += 1
        return zero >= threshold

    def next_query(self, state):
        if state.get('version') != QUERY_POLICY:
            raise ValueError('Original query policy version required')
        threshold = state.get('stall_threshold', 2)
        per = self._entries(state)
        eligible, stalled = [], []
        for index, direction in enumerate(self.directions):
            entries = per.get(direction['direction'], [])
            stalled_now = self._stalled(entries, threshold)
            if (self.cap is not None and len(entries) >= self.cap) or not self._unused(direction, state):
                # Exhausted directions still name the stall in the decision reason.
                if stalled_now:
                    stalled.append((len(entries), index, direction, entries))
                continue
            (stalled if stalled_now else eligible).append(
                (len(entries), index, direction, entries))
        if not eligible:
            return None
        eligible.sort(key=lambda item: (item[0], item[1]))
        _, index, direction, entries = eligible[0]
        last = entries[-1] if entries else None
        article_heavy = bool(last and last.get('article_hits', 0) * 2 >= max(1, last.get('raw_hits', 0)))
        reason = {'rule': QUERY_POLICY, 'selected_direction': direction['direction'],
                  'selected_category': direction['category'], 'completed_in_direction': len(entries),
                  'seed_order': index,
                  'switched_from_stalled': sorted(d['direction'] for _, _, d, _ in stalled),
                  'article_heavy_last_query': article_heavy,
                  'stall_threshold': threshold}
        for query in self._unused(direction, state):
            return {'query': query, 'direction': direction['direction'],
                    'category': direction['category'], 'reason': reason}


def record_query_outcome(state, *, direction, query, stats):
    key = normalize_query(query)
    if key in state['queries'] or key in state['blocked']:
        return state
    state = deepcopy(state)
    state['queries'][key] = {'query': query, 'direction': direction, **stats}
    state['order'].append(key)
    return state


def fold_query_state(pool_pool, run_id, policy):
    """Each batch checkpoints its full cumulative planner state; resume reads the latest."""
    with pool_pool.connect() as con:
        row = con.execute("SELECT value FROM checkpoints WHERE run_id=? AND key LIKE 'entry-query/stats/%'"
                          ' ORDER BY created DESC, key DESC LIMIT 1', (run_id,)).fetchone()
    state = policy.initial_state()
    if row:
        saved = json.loads(row['value'])
        if saved.get('version') != QUERY_POLICY:
            raise ValueError('Original query policy state version required')
        state.update(saved)
    state['stall_threshold'] = policy.stall_threshold
    state['per_direction_cap'] = policy.cap
    return state


def extract_entry_hints(row):
    """Optional hints live in source context; broken suggestions never block an entry."""
    hints, issues = {}, []
    value = row.get('category_hint')
    if value is None or value == 'UNKNOWN':
        hints['category_hint'] = value
    elif value in BUSINESS_CATEGORIES:
        hints['category_hint'] = value
    else:
        hints['category_hint'] = 'UNKNOWN'
        issues.append('unrecognized category_hint kept UNKNOWN')
    for key in ('business_kind', 'source_type'):
        item = row.get(key)
        if item is None or isinstance(item, str) and item.strip():
            hints[key] = item
        else:
            hints[key] = None
            issues.append('invalid ' + key + ' kept empty')
    goal = row.get('suggested_goal')
    if goal is not None:
        if isinstance(goal, dict) and set(goal) <= {'kind', 'entity', 'parameters'} \
                and all(isinstance(goal.get(k), str) and normalize(goal[k]) for k in ('kind', 'entity')) \
                and isinstance(goal.get('parameters'), dict):
            try:
                normalize(goal['parameters'])
                hints['suggested_goal'] = goal
            except ValueError:
                issues.append('unnormalizable suggested_goal parameters dropped')
        else:
            issues.append('malformed suggested_goal dropped')
    if row.get('requested_goal') is not None:
        issues.append('model-supplied requested_goal ignored: frozen goals come only from trusted caller parameters')
    for key in ('user_requires', 'user_requested', 'caller_goal'):
        if row.get(key) is not None:
            issues.append('model self-declared caller authority ignored: ' + key)
    return hints, issues


def foreign_application_claim(row, hit):
    """An A-site article recommending a B tool is a valid A content entry, but a
    row claiming the linked entry belongs to B (a foreign host) is rejected."""
    claims = []
    goal = row.get('suggested_goal')
    if isinstance(goal, dict) and isinstance(goal.get('entity'), str):
        claims.append(goal['entity'])
    claims.extend(row[key] for key in ('application', 'claimed_host', 'application_domain') if isinstance(row.get(key), str))
    for text in claims:
        match = _LEADING_DOMAIN.match(text)
        if match and host_identity('https://' + match[1] + '/') != host_identity(hit['uri']):
            return ('row claims the linked entry belongs to another application host ' + match[1]
                    + '; source is bound to ' + host_identity(hit['uri']))
    return None



def _prior_search_status(pool_pool, run_id, query=None):
    """Original search identities for this session; UNKNOWN/auth holds never resend."""
    with pool_pool.connect() as con:
        rows = con.execute("SELECT payload,result,state FROM tool_requests WHERE run_id=? AND kind='search'",
                           (run_id,)).fetchall()
    from .discovery_tools import search_channel_hold
    auth_hold = bool(search_channel_hold(pool_pool, run_id))
    for row in rows:
        detail = json.loads(row['result'] or '{}')
        if row['state'] == 'unknown' and detail.get('http_status') in (401, 403):
            auth_hold = True
        if query is not None and json.loads(row['payload']).get('search_query') == query and row['state'] in ('reserved', 'unknown'):
            return 'blocked', row['state'], detail.get('http_status'), auth_hold
    return ('seen', None, None, auth_hold) if query is not None and any(
        json.loads(r['payload']).get('search_query') == query for r in rows) else ('new', None, None, auth_hold)


def _check_entry_sources(scope, hits):
    """Source references may carry metadata in addition to the bound path and digest."""
    from webcollect.current_chain import assert_current_evidence
    assert_current_evidence(scope, [{k: hit['reference'][k] for k in ('path','sha256')} for hit in hits])


def _search_cooldown(pool,run_id):
    with pool.connect() as con:
        recent=con.execute("SELECT finished,json_extract(result,'$.http_status') AS status,"
                           "json_extract(result,'$.retry_after_seconds') AS retry FROM tool_requests "
                           "WHERE run_id=? AND kind='search' ORDER BY started DESC LIMIT 5",(run_id,)).fetchall()
    streak=0
    for r in recent:
        if r['status']!=429:break
        streak+=1
    if streak:
        delay=max(recent[0]['retry'] or 0,60*2**(streak-1))
        remaining=recent[0]['finished']+delay-time.time()
        if remaining>0:time.sleep(remaining)


_TASKED_PAIRS_CACHE = {}


def _registry_tasked_pairs(pool, batch):
    """(entry_url, requested_goal) pairs already holding consumer registry
    tasks, resolved once per producer batch run. Legacy batches without a
    chain manifest return an empty set (no behavior change)."""
    from webcollect.planning import canonical as _canonical
    from webcollect.candidate_consumer import tasked_entry_index
    key = (str(pool.path), batch)
    if key in _TASKED_PAIRS_CACHE:
        return _TASKED_PAIRS_CACHE[key]
    with pool.pool.connect() as con:
        frozen = con.execute('SELECT config FROM runs WHERE id=?', (batch,)).fetchone()
    manifest = json.loads(frozen[0]).get('current_chain_manifest') if frozen else None
    if not manifest:
        pairs = frozenset()
    else:
        from webcollect.current_chain import read_chain_scope
        scope = read_chain_scope(Path(manifest['path']).absolute())
        pairs = frozenset(tasked_entry_index(scope['registry']))
    _TASKED_PAIRS_CACHE[key] = pairs
    return pairs


def _application_pending_cap(pool, batch):
    """Per-application pending inventory ceiling from the frozen batch config
    (default 100). The 2026-11-06 stock audit found one application holding
    17.7% of all pending pages; over-concentrated supply is a single point of
    failure once that site rots."""
    with pool.pool.connect() as con:
        frozen = con.execute('SELECT config FROM runs WHERE id=?', (batch,)).fetchone()
    return int((json.loads(frozen[0]) if frozen else {}).get('application_pending_cap', 100))


def _app_pending_over_limit(pool, batch, application_id, header, row):
    if not application_id:
        return None
    snapshot = application_pending_remaining(pool, batch, application_id)
    if snapshot['remaining'] > 0:
        return None
    reason = (f"APP_NEW_TARGET: cumulative distinct NEW {snapshot['new_count']} >= {snapshot['new_target']}"
              if snapshot.get('new_target') is not None and snapshot['new_count'] >= snapshot['new_target']
              else f"APP_PENDING_CAP: application pending inventory {snapshot['pending']} >= {snapshot['cap']}")
    return pool.record_row_conclusion(header, result='OVER_LIMIT', reason=reason, original_row=row)


def application_pending_remaining(pool, batch, application_id):
    """Read-only scheduling headroom for the producer pipeline preflight.

    Reuses the same frozen application_pending_cap source as the final
    publication check; it never writes a quota ledger of its own. The
    CandidatePool publication transaction rechecks both limits authoritatively."""
    if not application_id:
        return None
    cap = _application_pending_cap(pool, batch)
    with pool.pool.connect() as con:
        pending = con.execute("SELECT COUNT(*) FROM data_candidates WHERE application_id=? AND state='pending'",
                              (application_id,)).fetchone()[0]
        frozen = con.execute('SELECT config FROM runs WHERE id=?', (batch,)).fetchone()
        target = (json.loads(frozen[0]) if frozen else {}).get('application_new_target')
        new_count = con.execute(
            "SELECT COUNT(DISTINCT c.candidate_id) FROM data_candidates c "
            "JOIN candidate_batch_rows b ON b.candidate_id=c.candidate_id "
            "WHERE c.application_id=? AND b.result='NEW'", (application_id,)).fetchone()[0] if target is not None else None
    remaining = max(0, cap - pending)
    if target is not None:remaining = min(remaining, max(0, target - new_count))
    return {'pending': pending, 'cap': cap, 'remaining': remaining,
            **({'new_target': target, 'new_count': new_count} if target is not None else {})}


def _publish_entry(pool, ledger, batch, root, header, candidate, source, row, *, application_id=None):
    prior = pool.batch_row_identity(header['row_id'])
    if prior:
        if prior[0] != header['response_sha256']:
            raise ValueError('Frozen entry response changed')
        return prior[1]
    # Reuse the original rendered observation; never issue a replacement GET.
    from .producer_observation import from_pool
    shared_language = from_pool(pool, ledger, candidate['entry_url'])
    if shared_language is not None:
        from .page_consumption import blank_frame_exclusion, required_login_exclusion
        blank = blank_frame_exclusion(shared_language[1]) or required_login_exclusion(shared_language[1])
        if blank:
            return pool.record_row_conclusion(header, result='REJECTED',
                reason=blank['reason'], original_row={**row, 'visible_frame_exclusion': blank})
        from webcollect.page_language import assess as assess_language
        from webcollect.batch_core import load_json
        language = assess_language(load_json(shared_language[1]['observation']['path']))
        if language['excluded']:
            return pool.record_row_conclusion(header, result='REJECTED',
                reason='rendered_chinese_not_evidenced', original_row={**row,
                    'language_exclusion':language,'observation':shared_language[1]['observation']})
    if pool.consumption(candidate['entry_url'],kind=candidate.get('candidate_kind')):
        return pool.record_row_conclusion(header,result='REJECTED',reason='NO_CONSUME: producer image-only page exclusion',original_row=row)
    over = _app_pending_over_limit(pool, batch, application_id, header, row)
    if over is not None:
        return over
    from webcollect.planning import canonical as _canonical
    from webcollect.candidate_consumer import normalize_entry_url
    if ((normalize_entry_url(candidate['entry_url']), _canonical(candidate.get('requested_goal')))
            in _registry_tasked_pairs(pool, batch)):
        return pool.record_row_conclusion(header, result='REJECTED',
            reason='TASKED_URL_DUPLICATE: consumer registry already holds this entry URL and goal', original_row=row)
    if source.get('table_policy'):
        try:
            app = pool.pool.application(candidate['entry_url'])
            application_id = application_id or (app or {}).get('id')
            over = _app_pending_over_limit(pool, batch, application_id, header, row)
            if over is not None:
                return over
            source = site_tables.Discovery(pool).source(application_id,candidate['entry_url'],source)
            if ('expected_site_decision_id' in source
                    and source['expected_site_decision_id'] != source['site_decision_id']):
                raise ValueError('Frozen batch site decision changed; retain original row for review')
            with pool.pool.connect() as con:
                frozen=con.execute('SELECT config FROM runs WHERE id=?',(batch,)).fetchone()
            manifest=json.loads(frozen[0]).get('current_chain_manifest') if frozen else None
            if manifest:
                from webcollect.current_chain import read_chain_scope,assert_current_evidence
                verify_evidence([manifest])
                assert_current_evidence(read_chain_scope(Path(manifest['path']).absolute()),source['references'])
            duplicate = selection.existing_candidate(pool,candidate,application_id)
            if duplicate:
                with pool.pool.connect() as con:
                    old_sources=[json.loads(r[0]) for r in con.execute('SELECT source FROM candidate_sources WHERE candidate_id=?',(duplicate,))]
                    old_state=con.execute('SELECT state FROM data_candidates WHERE candidate_id=?',(duplicate,)).fetchone()[0]
                if old_state in ('failed','reconcile') or selection.confirmed_category([*old_sources,source]) != source['category_hint']:
                    raise ValueError('Original row is quarantined, unsettled or classification-conflicted; no replacement')
                return pool.publish_row(header,candidate,source,application_id=application_id)
        except ValueError as error:
            return pool.record_row_conclusion(header,result='REJECTED',reason=str(error),original_row=row)
    if source.get('selection_version') == selection.VERSION:
        duplicate = selection.existing_candidate(pool, candidate, application_id)
        if duplicate:
            return pool.publish_row(header,candidate,source,application_id=application_id)
    try:
        shared=None
        if not source.get('entry_recheck'):
            from .producer_observation import entry_receipt
            shared=entry_receipt(pool,ledger,candidate['entry_url'],root)
            if shared is None:
                raise OutcomeUnknown('Original supply observation missing; no replacement GET')
        access, ref = shared if shared else check_entry(ledger,batch,candidate['entry_url'],root,recheck=source.get('entry_recheck'))
    except (SiteStopped,OutcomeUnknown) as held:
        if isinstance(held,OutcomeUnknown) and not source.get('required_supply_kind'):raise
        return pool.record_row_conclusion(header,result='HELD',reason=str(held),original_row=row)
    if access['result'] != 'PASS':
        return pool.record_row_conclusion(header,result=access['result'],original_row=row,entry_http=ref,
                                          reason=access['reason'] or 'No confirmed entry HTTP response')
    source = {**source, 'entry_http':ref, 'references':[*source['references'],ref]}
    try:
        return pool.publish_row(header,candidate,source,application_id=application_id)
    except ValueError as error:
        if not source.get('table_policy'): raise
        return pool.record_row_conclusion(header,result='REJECTED',reason=str(error),original_row=row,entry_http=ref)


def produce_entries(config, *, pool_path, ledger_path, output=None, history_set=None, queries=(), sources=(), directions=(),
                    goals_path=None, target=1000, max_searches=None, max_batches=None, batch_size=50,
                    search_engine=None, stall_threshold=2, per_direction_cap=None, batch_key=None,
                    excluded_applications=(), discovery_mode=None, feedback_scope=None,
                    search_count=10, entry_selection='rule', categories=(), probe_search_hold=None, dispatch_holds=None,
                    producer_pipeline=None, producer_optimization=None, application_pending_cap=None, application_new_target=None, allowed_hosts=(), site_expansion=False, prefer_simplified_chinese=False):
    """Entry/target candidate producer on webcollect-data-candidate-2.

    Per-response-row publication with stable identities; interruption resumes
    from the original response only. No browser, no full-pool entity loads.
    """
    if producer_pipeline not in (None, 'serial', 'overlap-1'):
        raise ValueError('producer_pipeline must be serial or overlap-1')
    if (any(type(n) is not int or n < 1 for n in (target, batch_size))
            or any(type(n) is not int or n < 1 for n in (max_searches, max_batches) if n is not None)
            or batch_size > 100):
        raise ValueError('Positive bounded target/budgets and batch size <=100 required')
    if search_engine not in (None, 'public', 'search_std', 'search_pro'):
        raise ValueError('Unsupported search engine')
    if type(search_count) is not int or not 1 <= search_count <= 50:
        raise ValueError('Search result count must be 1–50')
    if (probe_search_hold or dispatch_holds) and (not categories or discovery_mode!='new-sites' or queries or sources or directions or goals_path):
        raise ValueError('Search probe and dispatch holds require a category-only new-sites batch')
    if not queries and not sources and not directions and not categories and goals_path is None:
        raise ValueError('Explicit queries, directions, goals or evidence-backed sources required')
    pool = CandidatePool(pool_path)
    pool._require_v2()
    session_id = config['run_id']
    scope_tail = batch_key or 'main'
    if not isinstance(scope_tail, str) or not scope_tail or len(scope_tail) > 80:
        raise ValueError('Bounded explicit batch key required')
    run_id = session_id + '/entry-batch/' + scope_tail
    with pool.pool.connect() as con:
        frozen_rows = {r['id']: json.loads(r['config']) for r in con.execute(
            'SELECT id,config FROM runs WHERE id IN (?,?)', (session_id,run_id))}
    previous = frozen_rows.get(session_id, {})
    previous_batch = frozen_rows.get(run_id, {})
    category_only=bool(categories and discovery_mode=='new-sites' and not (queries or sources or directions or goals_path))
    if search_engine is None:
        search_engine=previous_batch.get('search_engine') or ('public' if category_only else 'search_std')
    scoped_expand=bool(discovery_mode=='expand' and allowed_hosts)
    if search_engine=='public' and (not (category_only or scoped_expand) or probe_search_hold):
        raise ValueError('Public search requires category-only new-sites. A paid probe requires an explicit BigModel search engine.')
    table_policy = previous_batch.get('table_policy') if previous_batch else site_tables.POLICY
    if table_policy:
        if table_policy != site_tables.POLICY: raise ValueError('Unsupported frozen site-table policy')
        site_tables.Discovery(pool,install=True)
    if previous_batch:
        if max_batches is None:
            max_batches = previous_batch['max_batches']
        if max_searches is None:
            max_searches = previous_batch['max_searches']
        if per_direction_cap is None:
            per_direction_cap = previous_batch.get('query_policy',previous_batch).get('per_direction_cap')
    http_binding = _entry_http_binding(frozen_rows.get(run_id),config)
    # The grounded business-content entry pipeline is the only producer path.
    # A frozen batch resumes with its recorded run-config metadata as data.
    model_protocol = (previous_batch or previous).get('model_protocol') or 'entry-tools'
    from .grounded_entries import produce as produce_grounded
    return produce_grounded(config,pool_path=pool_path,ledger_path=ledger_path,output=output or previous_batch.get('output'),
        history_set=history_set or previous.get('current_chain_manifest',{}).get('path'),
        queries=queries,sources=sources,directions=directions,goals_path=goals_path,target=target,
        max_searches=max_searches,max_batches=max_batches,batch_size=batch_size,search_engine=search_engine,
        stall_threshold=stall_threshold,per_direction_cap=per_direction_cap,batch_key=batch_key,
        excluded_applications=excluded_applications,discovery_mode=discovery_mode,feedback_scope=feedback_scope,
        search_count=search_count,entry_selection=entry_selection,model_protocol=model_protocol,categories=categories,
        probe_search_hold=probe_search_hold,dispatch_holds=dispatch_holds,producer_pipeline=producer_pipeline,
        producer_optimization=producer_optimization, application_pending_cap=application_pending_cap, application_new_target=application_new_target, allowed_hosts=allowed_hosts, site_expansion=site_expansion, prefer_simplified_chinese=prefer_simplified_chinese)
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    init=sub.add_parser('install'); init.add_argument('--pool',required=True); init.add_argument('--create-pool',action='store_true')
    entry=sub.add_parser('produce-entries',help='candidate-producer-3 entry/target protocol; requires candidate-pool-2 install')
    for name in ('config','ledger','pool'): entry.add_argument('--'+name,required=True)
    entry.add_argument('--history-set',type=Path,help='Current-chain manifest used by the consumer; derives the evidence directory by default')
    entry.add_argument('--output',help='Explicit evidence directory (must be inside the chain when --history-set is used)')
    entry.add_argument('--category',action='append',default=[],help='Target category; host freezes an Agent search plan when no explicit terms are given')
    entry.add_argument('--search-engine',choices=['public','search_std','search_pro'],
                       help='Category-only new sites default to public search. BigModel search requires an explicit choice.')
    entry.add_argument('--probe-search-hold',help='Permit one new business query against this original 1113, preserving the old request')
    entry.add_argument('--dispatch-holds',type=Path,help='Negative host and URI constraints from this project')
    entry.add_argument('--query',action='append',default=[],help='Plain seed queries (single implicit direction)')
    entry.add_argument('--sources',help='JSON list of uri/title/content/reference')
    entry.add_argument('--directions',help='JSON file: [{"direction","category","queries":[...]}]')
    entry.add_argument('--goals',help='JSON file {"schema_version":"webcollect-caller-goals-1","goals":[{"uri","requested_goal"}]}')
    entry.add_argument('--discovery-mode', choices=['new-sites','expand','mixed'])
    entry.add_argument('--entry-selection', choices=['rule','model'], default='rule',
                       help='entry-tools-3: conservative HTML rules or evidence-bound model link selection')
    entry.add_argument('--producer-pipeline', choices=['serial','overlap-1'],
                       help='Scheduling mode only; default serial keeps the original observe->judge->publish order. '
                            'overlap-1 additionally moves the app pending-cap preflight ahead of browser/model and '
                            'prefetches the next chunk screen behind the current classify/publish (same prepared unit).')
    entry.add_argument('--producer-optimization', choices=['observation-feedback-1'],
                       help='Opt-in for a new entry-tools-13 batch: bounded readiness, confirmed HTTP failure receipts and query feedback.')
    entry.add_argument('--feedback-scope',type=Path,help='Explicit original consumer scope; read-only feedback frozen for this batch')
    entry.add_argument('--application-new-target', type=int, help='New batch: cumulative distinct NEW per application across this project, regardless of consumption state')
    entry.add_argument('--application-pending-cap', type=int, help='Explicit pending ceiling frozen for this new batch')
    entry.add_argument('--prefer-simplified-chinese', action='store_true', help='New site-expansion batch: prefer simplified Chinese routes without excluding other Chinese pages')
    entry.add_argument('--site-expansion', action='store_true', help='Persist and drain same-host link queue before supplementary search (new entry-tools-13 batch)')
    entry.add_argument('--allowed-host', action='append', default=[], help='Exact hostname allowed in this batch')
    entry.add_argument('--batch-key')
    entry.add_argument('--search-count',type=int,default=10,help='Requested results per distinct search, 1–50')
    entry.add_argument('--excluded-applications',help='JSON list of URIs whose original model application is unresolved')
    for name,default in (('target',1000),('max-searches',None),('max-batches',None),('batch-size',50),
                         ('stall-threshold',2),('per-direction-cap',None)):
        entry.add_argument('--'+name,type=int,default=default)
    a=p.parse_args(argv)
    if a.command=='install':
        if a.create_pool: SitePool(a.pool,initialize=True)
        print(json.dumps(CandidatePool(a.pool,install=True).stats())); return
    if a.command=='produce-entries':
        print(json.dumps(produce_entries(load_json(a.config),pool_path=a.pool,ledger_path=a.ledger,output=a.output,history_set=a.history_set,
            queries=a.query,sources=load_json(a.sources) if a.sources else (),
            directions=read_directions(a.directions) if a.directions else (),
            goals_path=Path(a.goals).absolute() if a.goals else None,target=a.target,max_searches=a.max_searches,
            max_batches=a.max_batches,batch_size=a.batch_size,stall_threshold=a.stall_threshold,
            per_direction_cap=a.per_direction_cap,batch_key=a.batch_key,discovery_mode=a.discovery_mode,feedback_scope=a.feedback_scope,entry_selection=a.entry_selection,
            search_count=a.search_count, search_engine=a.search_engine, categories=a.category, probe_search_hold=a.probe_search_hold, dispatch_holds=a.dispatch_holds, excluded_applications=load_json(a.excluded_applications) if a.excluded_applications else (),
            producer_pipeline=a.producer_pipeline,producer_optimization=a.producer_optimization,application_pending_cap=a.application_pending_cap,application_new_target=a.application_new_target,allowed_hosts=a.allowed_host,site_expansion=a.site_expansion,prefer_simplified_chinese=a.prefer_simplified_chinese),
            ensure_ascii=False));return
    raise ValueError('Unknown command: '+a.command)


if __name__=='__main__': main()
