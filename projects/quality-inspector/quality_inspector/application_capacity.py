"""Application capacity over explicit effective sample sets, never pending work."""
from collections import Counter
from urllib.parse import urlsplit

LIMIT = 500


def application_key(uri, registry=None):
    if registry:
        app=registry.application(uri)
        if not app: raise ValueError('Effective sample application missing from bound registry')
        return app['id']
    host=urlsplit(uri).hostname
    if not host: raise ValueError('Effective site needs a valid application URI')
    host=host.lower().rstrip('.')
    return host[4:] if host.startswith('www.') else host


def admit(existing, proposed, *, limit=LIMIT):
    """A deterministic planning projection; callers still verify the actual set.

    Repeated IDs and replacement copies consume one slot. A sample cannot move
    to another application. No approval or persistent counter is fabricated.
    """
    members={}; counts=Counter()
    for item in existing:
        sid,aid=item['sample_id'],item['application_id']
        if sid in members and members[sid]!=aid: raise ValueError('Effective sample changes application')
        members[sid]=aid
    counts.update(members.values())
    if any(n>limit for n in counts.values()): raise ValueError('Existing effective set exceeds application capacity')
    accepted=[]; rejected=[]; repeats=[]
    for item in proposed:
        sid,aid=item['sample_id'],item['application_id']
        if sid in members:
            if members[sid]!=aid: raise ValueError('Effective sample changes application')
            repeats.append(sid)
        elif counts[aid]>=limit: rejected.append(sid)
        else:
            members[sid]=aid;counts[aid]+=1;accepted.append(sid)
    return {'limit':limit,'counts':dict(counts),'accepted_sample_ids':accepted,
            'over_capacity_sample_ids':rejected,'already_effective_sample_ids':repeats,
            'scope':'explicit_effective_delivery_set','acceptance':'NOT_EVALUATED'}
