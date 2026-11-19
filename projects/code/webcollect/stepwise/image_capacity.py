import json

from ..failure_policy import GlobalFailure


EVENT = 'stepwise_final_images'
STAGE_IMAGES = {'decision': (1, 1), 'writeback': (2, 2), 'judgement': (1, 3)}


class FinalImagesUnavailable(GlobalFailure):
    code = 'STEPWISE_FINAL_IMAGES_UNAVAILABLE'
    failure_class = 'configuration'


def image_authorization(connection, config):
    if not config.get('run_id'):
        return None
    row = connection.execute('SELECT detail FROM batch_events WHERE event=? ORDER BY seq DESC LIMIT 1', (EVENT,)).fetchone()
    if not row:
        return None
    decision = json.loads(row[0])
    if (decision.get('run_id') != config['run_id'] or decision.get('model') != config['model']['model']
            or decision.get('max_images') != 3 or type(decision.get('after_job_rowid')) is not int
            or decision['after_job_rowid'] < 0):
        raise FinalImagesUnavailable('STEPWISE_FINAL_IMAGES_UNAVAILABLE: invalid consumer image authorization')
    return decision


def authorize_final_images(ledger, reason):
    model = ledger.config['model']
    if not isinstance(reason, str) or not reason.strip() or model.get('supports_vision', True) is not True:
        raise ValueError('Explicit reason and a vision-capable consumer model required')
    with ledger.transaction() as connection:
        ledger.require_consumer_ledger(connection)
        decision = image_authorization(connection, ledger.config)
        if decision is None:
            decision = {'run_id': ledger.config['run_id'], 'model': model['model'], 'max_images': 3,
                        'after_job_rowid': connection.execute('SELECT coalesce(max(rowid),0) FROM jobs').fetchone()[0],
                        'reason': reason}
            ledger.event(connection, EVENT, decision)
    ledger.stepwise_image_authorization = decision
    return decision


def require_image_capacity(config, *, ledger=None, connection=None, job_id=None):
    model = config.get('model') or {}
    limit = model.get('max_images')
    if model.get('supports_vision', True) is True and type(limit) is int and limit > 0:
        if limit >= 3:
            return limit
        decision = (image_authorization(connection, config) if connection is not None
                    else getattr(ledger, 'stepwise_image_authorization', None))
        if isinstance(decision, dict):
            if job_id is None:
                return decision['max_images']
            cutoff = decision['after_job_rowid']
            with ledger.connect() as current:
                permitted = current.execute("""
                    SELECT 1 FROM jobs child LEFT JOIN jobs parent ON parent.id=json_extract(child.payload,'$.parent_job_id')
                    WHERE child.id=? AND child.kind='stepwise-decision' AND child.rowid>?
                    AND (json_extract(child.payload,'$.parent_job_id') IS NULL OR parent.rowid>?)
                    """, (job_id, cutoff, cutoff)).fetchone()
            if permitted:
                return decision['max_images']
    raise FinalImagesUnavailable(
        f'STEPWISE_FINAL_IMAGES_UNAVAILABLE: 回写需要 2 张原图，独立判定最多需要 3 张原图；'
        f'max_images={limit}, supports_vision={model.get("supports_vision", True)}')
