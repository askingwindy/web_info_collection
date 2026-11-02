"""Bounded per-site planning rounds in the original job ledger. Never collects."""
import argparse
import json
from pathlib import Path
from .batch_core import load_json, save_json, file_sha, BatchLedger
from .planning import object_sha256, verify_evidence

VERSION = 'site-rolling-fragments-1'


def plan_round(ledger, catalog, site_uri, output, *, history_registry=None, history_set=None,
               page_identities=None, feedback=(), synthetic_specs=None, max_tasks=None, controlled=False):
    from .task_generation import generate
    if max_tasks is not None and (type(max_tasks) is not int or max_tasks < 1):
        raise ValueError('An explicit route count must be positive')
    records = [r for r in load_json(catalog)['records'] if r.get('site_uri') == site_uri]
    if not records:
        raise ValueError('Site must exist in the actual observed capability catalog')
    output = Path(output).resolve()
    from .application_identity import host_key
    site_key = host_key(site_uri)
    if page_identities is None:
        from .single_record import identity
        pages = {}
        for number, record in enumerate(records):
            one = output/f'identity-catalog-{number}.json'
            save_json(one, {'schema_version':'webcollect-capability-catalog-1',
                           'mode':ledger.config['mode'],'records':[record]})
            result = identity(one, output/f'identity-{number}.json', registry=history_registry)
            pages.update(result['pages'])
        page_identities = output/'page-identities.json'
        save_json(page_identities, {'schema_version':'webcollect-page-identities-1','pages':pages})
    with ledger.transaction() as con:
        con.execute('CREATE TABLE IF NOT EXISTS site_planning_rounds ('
            'site TEXT NOT NULL, round INTEGER NOT NULL, output TEXT UNIQUE NOT NULL, '
            'state TEXT NOT NULL, context TEXT NOT NULL, result TEXT, PRIMARY KEY(site,round))')
        rows = con.execute('SELECT round,output,state,context,result FROM site_planning_rounds WHERE site=? ORDER BY round',
                           (site_key,)).fetchall()
        own = next((r for r in rows if r[1] == str(output)), None)
        if own:
            saved_context=json.loads(own[3])
            if max_tasks is None:
                max_tasks = saved_context['max_routes']
            if (saved_context['catalog_sha256'] != file_sha(catalog) or saved_context['site_uri'] != site_uri
                    or saved_context['max_routes'] != max_tasks or saved_context.get('controlled',False) != controlled):
                raise ValueError('Existing rolling round input changed; do not reuse a different scope')
            if own[2] != 'done':
                raise ValueError('Original round is unresolved; reconcile its job, do not create another request')
            receipt = load_json(output/'round-receipt.json')
            verify_evidence([receipt['generation_result']])
            return receipt
        # A pre-enqueue failure closed with a recorded reason made no request; it is
        # neither history to consult nor an unresolved UNKNOWN blocking the site.
        unresolved = [r for r in rows if r[2] not in ('done', 'failed')]
        if unresolved:
            raise ValueError('A prior round is unresolved; no new round or UNKNOWN resend')
        history = []
        for row in rows[-10:]:
            if row[2] == 'failed':
                continue
            prior = load_json(Path(row[1])/'round-receipt.json')
            verify_evidence([prior['generation_result']])
            history.append({'round': row[0], 'result': load_json(prior['generation_result']['path'])})
        feedback = list(feedback)
        if feedback:
            verify_evidence(feedback)
        from .runtime import _bound_quality_report
        for ref in feedback:
            _bound_quality_report([ref])  # Planning prose cannot self-issue QC failures.
        from .agent_feedback import site_context
        actual_feedback = site_context(history_registry, site_uri, generation=history, quality=feedback, model_ledger=ledger)
        if actual_feedback['unresolved']:
            raise ValueError('Original execution/model request remains unresolved; reconcile before next round')
        context = {'version': VERSION, 'site_uri': site_uri, 'application_key': site_key, 'round': len(rows)+1,
            'catalog_sha256': file_sha(catalog), 'history': history,
            'quality_feedback': [{'reference': ref, 'report': load_json(ref['path'])} for ref in feedback],
            'max_routes': max_tasks, 'actual_feedback':actual_feedback, 'images':actual_feedback['images'],
            'controlled':controlled}
        if history and history[-1]['result'].get('pending'):
            raise ValueError('Previous model/generation work remains pending; reconcile original ledger')
        if len(history) >= 2 and all(h['result'].get('generated_tasks') == 0 for h in history[-2:]):
            raise ValueError('Two empty/rejected rounds: stop this site and retain reasons')
        con.execute('INSERT INTO site_planning_rounds VALUES(?,?,?,?,?,NULL)',
                    (site_key, len(rows)+1, str(output), 'running', json.dumps(context, ensure_ascii=False)))
    result = generate(ledger, catalog, output/'generation', generator='agent-model' if controlled else 'fragment-model',
        history_registry=history_registry, history_set=history_set, page_identities=page_identities,
        synthetic_specs=synthetic_specs, max_tasks=max_tasks, site_filter=site_uri, fragment_context=context)
    path = output/'generation'/'generation-result.json'
    if not path.exists():
        path = output/'generation-result.json'; save_json(path, result)
    receipt = {'schema_version': VERSION, 'site_uri': site_uri, 'context_sha256': object_sha256(context),
        'round': context['round'], 'generation_result': {'path': str(path), 'sha256': file_sha(path)},
        'generated_tasks': result['generated_tasks'], 'queue_job_id': result.get('queue_job_id'),
        'collection_started': False, 'QC_approval': False}
    save_json(output/'round-receipt.json', receipt)
    with ledger.transaction() as con:
        con.execute('UPDATE site_planning_rounds SET state=?,result=? WHERE site=? AND round=?',
                    ('pending' if result.get('pending') else 'done', json.dumps(receipt), site_key, context['round']))
    return receipt


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'ledger', 'catalog', 'site-uri', 'output'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--controlled', action='store_true'); p.add_argument('--history-registry'); p.add_argument('--history-set'); p.add_argument('--page-identities')
    a = p.parse_args(argv)
    print(json.dumps(plan_round(BatchLedger(a.ledger, load_json(a.config)), a.catalog, a.site_uri, a.output,
        history_registry=a.history_registry, history_set=a.history_set, page_identities=a.page_identities, controlled=a.controlled), ensure_ascii=False))


if __name__ == '__main__':
    main()
