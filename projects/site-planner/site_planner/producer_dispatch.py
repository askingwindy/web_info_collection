"""Early admission and ranking for first-party producer work."""
from collections import Counter, defaultdict, deque
from contextlib import contextmanager
import fcntl
from pathlib import Path
from urllib.parse import urlsplit

from .candidate_pool import candidate_dedup_key, entry_identity, landing_key


def candidates(link):
    return [{'candidate_kind':'entry' if goal is None else 'target', 'entry_url':link['uri'],
             'requested_goal':goal} for goal in link.get('producer_goals',[None])]


def unpublished(pool, link, landed_uri=None):
    remaining, existing = [], []
    with pool.pool.connect() as connection:
        for candidate in candidates(link):
            application = link['application_id']
            row = connection.execute('SELECT candidate_id FROM data_candidates WHERE dedup_key=? '
                'UNION ALL SELECT candidate_id FROM candidate_landings WHERE landing_key=? LIMIT 1',
                (candidate_dedup_key(candidate,application),landing_key(candidate,application,landed_uri or link['uri']))).fetchone()
            if row:existing.append(row[0])
            else:remaining.append(candidate['requested_goal'])
    return remaining, existing


@contextmanager
def dispatch_lock(pool, identity):
    database = Path(pool.path).resolve()
    directory = database.parent / (database.name+'.producer-locks')
    directory.mkdir(exist_ok=True)
    with (directory / identity).open('a+b') as handle:
        try:fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:yield False
        else:yield True


def claim_pages(pool,link,landed_uri,locks):
    available={}
    for candidate in candidates(link):
        key=landing_key(candidate,link['application_id'],landed_uri)
        if key not in available and locks.enter_context(dispatch_lock(pool,key)):
            available[key]=candidate['requested_goal']
    return list(available.values()),list(available)


def prior_dispatch(ledger, keys):
    with ledger.connect() as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='producer_purpose_dispatch'").fetchone():return None
        for key in keys:
            row = connection.execute('SELECT p.job_id,p.binding,j.state,r.id AS request_id,r.state AS request_state '
                'FROM producer_purpose_dispatch p JOIN jobs j ON j.id=p.job_id '
                'LEFT JOIN model_requests r ON r.job_id=j.id WHERE p.page=? '
                "AND (j.attempts>0 OR j.state!='queued' OR r.id IS NOT NULL) LIMIT 1",(key,)).fetchone()
            if row:return dict(row)
    return None


def remember_dispatch(ledger, job_id, pages):
    with ledger.transaction() as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS producer_purpose_dispatch '
            '(page TEXT PRIMARY KEY,job_id TEXT NOT NULL,binding TEXT NOT NULL)')
        connection.executemany('INSERT INTO producer_purpose_dispatch VALUES(?,?,?) '
            'ON CONFLICT(page) DO UPDATE SET job_id=excluded.job_id,binding=excluded.binding',
            [(key,job_id,record['binding']) for record in pages for key in record['dispatch_keys']])


def section(uri):
    parts=urlsplit(uri).path.strip('/').split('/')
    return parts[0].split('.')[0] if len(parts)==1 else parts[0]


def section_history(pool, application):
    with pool.pool.connect() as connection:
        results=connection.execute("SELECT json_extract(i.record,'$.uri'),json_extract(i.conclusion,'$.result'),"
            "json_extract(i.conclusion,'$.reason') FROM (SELECT scope_id FROM application_scopes "
            "WHERE application_id=? ORDER BY created DESC LIMIT 64) s JOIN application_scope_items i USING(scope_id) "
            "WHERE json_type(i.record,'$.uri')='text' AND i.conclusion IS NOT NULL "
            "ORDER BY i.rowid DESC LIMIT 512",(application,)).fetchall()
    stats=defaultdict(Counter);seen=set()
    for uri,result,reason in results:
        outcome='LANGUAGE' if reason=='simplified_chinese_not_evidenced' else result
        if outcome not in ('NEW','DUPLICATE','LANGUAGE','REJECTED'):continue
        identity=(entry_identity(uri),outcome)
        if identity not in seen:
            stats[section(uri)][outcome]+=1;seen.add(identity)
    return stats


def rank_sections(links, history, *, offset=0):
    known,unseen=[],deque()
    for position,link in enumerate(links):
        key=section(link['uri']);counts=history.get(key,{})
        total=sum(counts.values())
        link={**link,'section_yield':{'section':key,'settled':total,'new':counts.get('NEW',0)}}
        if total<3:unseen.append(link)
        else:known.append((-(counts.get('NEW',0)+1)/(total+2),position,link))
    ranked=deque(link for _,_,link in sorted(known));output=[]
    while ranked or unseen:
        explore=unseen and (not ranked or (offset+len(output))%5==4)
        output.append((unseen if explore else ranked).popleft())
    return output
