"""编号注册表：同一生产线须始终使用同一个 SQLite 文件。"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def write_json(path, data):
    path = Path(path)
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def ensure_registry_schema(con):
    """Create the original three tables, before starting a caller transaction."""
    con.executescript('''
      CREATE TABLE IF NOT EXISTS sites (
        id INTEGER PRIMARY KEY, uri TEXT NOT NULL UNIQUE,
        category TEXT NOT NULL, kind TEXT NOT NULL, next_sample INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, kind TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS allocations (
        sample_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, batch_id TEXT NOT NULL);
    ''')


def allocate_in_transaction(con, uri, category, sample_kind='integration', day=None, batch_id=None, *, category_metadata=False, required_site_id=None):
    """Reserve an ID inside an existing write transaction, without committing.

    Runtime callers persist the task/attempt mapping in this same transaction.
    A committed reservation is never recycled, including an unstarted attempt.
    Candidate tasks may freeze the producer-maintained Table1 site ID; legacy
    tasks retain the original registry-local allocation when it is absent.
    """
    if not con.in_transaction:
        raise ValueError('编号分配必须处于调用方写事务中')
    from .batch_protocol import guard_registry_site
    guard_registry_site(con, uri, category)
    if not re.match(r'^https?://[^\s/]+',uri) or not category.strip():
        raise ValueError('站点必须提供 HTTP(S) URI 和类目')
    if sample_kind not in ('integration', 'real'):
        raise ValueError('未知样本性质')
    if required_site_id is not None and (not re.fullmatch(r'S\d{6}', required_site_id) or required_site_id == 'S000000'):
        raise ValueError('Table1 站点编号格式不正确')
    day = day or datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
    if not re.fullmatch(r'\d{8}',day): raise ValueError('日期编号须为 YYYYMMDD')
    if batch_id is not None and not re.fullmatch(r'B\d{8}_\d{3,}',batch_id):
        raise ValueError('批次编号格式不正确')
    batch_prefix = batch_id.split('_')[0] if batch_id else 'B' + day
    floors = {}
    has_floors = con.execute("SELECT 1 FROM sqlite_master WHERE name='allocation_floors'").fetchone()
    if has_floors:
        floors = dict(con.execute('SELECT name,last_number FROM allocation_floors WHERE name IN (?,?)',('site',batch_prefix)))
    if batch_id and batch_prefix in floors and int(batch_id.split('_')[1]) <= floors[batch_prefix]:
        raise ValueError('批次编号已在上一代预留')
    row=con.execute('SELECT id,category,kind,next_sample FROM sites WHERE uri=?',(uri,)).fetchone()
    if row:
        site_number,old_category,kind,seq=row
        if kind != sample_kind or (old_category != category and not category_metadata):
            raise ValueError('已有 URI 的类目或样本性质不同，不允许静默变更')
        if required_site_id is not None and site_number != int(required_site_id[1:]):
            raise ValueError('Table1 站点编号与现有交付账本不一致')
    else:
        site_number=(int(required_site_id[1:]) if required_site_id is not None else
                     max(con.execute('SELECT COALESCE(MAX(id),0) FROM sites').fetchone()[0],floors.get('site',0))+1)
        if site_number > 999999: raise ValueError('站点编号已超出六位范围')
        if site_number <= floors.get('site',0) or con.execute('SELECT 1 FROM sites WHERE id=?',(site_number,)).fetchone():
            raise ValueError('Table1 站点编号已被其他站点或历史编号下限占用')
        seq=1
        con.execute('INSERT INTO sites VALUES(?,?,?,?,?)',(site_number,uri,category,sample_kind,seq))
    site_id=f'S{site_number:06}'
    if batch_id is None:
        prefix=f'B{day}_'
        if has_floors:
            last=con.execute('SELECT COALESCE(MAX(CAST(substr(id,11) AS INTEGER)),0) FROM batches WHERE id LIKE ?',(prefix+'%',)).fetchone()[0]
            batch_seq=max(last,floors.get(batch_prefix,0))+1
        else:
            batch_seq=con.execute('SELECT COUNT(*)+1 FROM batches WHERE id LIKE ?',(prefix+'%',)).fetchone()[0]
        batch_id=f'{prefix}{batch_seq:03}'
    sample_id=f'{site_id}_sample_{seq:06}'
    existing=con.execute('SELECT kind FROM batches WHERE id=?',(batch_id,)).fetchone()
    if existing and existing[0]!=sample_kind:raise ValueError('批次样本性质不同')
    if not existing:con.execute('INSERT INTO batches VALUES(?,?)',(batch_id,sample_kind))
    con.execute('INSERT INTO allocations VALUES(?,?,?)',(sample_id,site_id,batch_id))
    con.execute('UPDATE sites SET next_sample=? WHERE id=?',(seq+1,site_number))
    return {'batch_id':batch_id,'sample_id':sample_id,'site_id':site_id}


def allocate(registry, uri, category, sample_kind='integration', day=None, batch_id=None):
    """事务分配站点、批次与一个样本；失败保留空号，不回收已分配编号。"""
    registry = Path(registry)
    registry.parent.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(registry,timeout=30)
    try:
        ensure_registry_schema(con)
        con.execute('BEGIN IMMEDIATE')
        result=allocate_in_transaction(con,uri,category,sample_kind,day,batch_id)
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def verify_existing_registry(registry, output_parent):
    """续采前核对同一数据根目录的既有批次，防止丢失/误用账本后复用编号。"""
    registry=Path(registry).resolve();parent=Path(output_parent)
    batches=[p for p in parent.iterdir() if p.is_dir() and ((p/'samples').exists() or (p/'evidence').exists())] if parent.exists() else []
    if not batches:return
    if not registry.is_file():raise ValueError('数据目录已有采集批次但编号账本缺失；请恢复原账本，不允许重新分配编号')
    try:
        from contextlib import closing
        with closing(sqlite3.connect(registry.as_uri()+'?mode=ro',uri=True)) as con:
            for batch in batches:
                manifest_path=batch/'manifest.json'
                if not manifest_path.exists():continue  # Incomplete attempts still retain their reservations in this ledger.
                manifest=json.loads(manifest_path.read_text())
                if manifest.get('sample_kind')!='real':continue
                for site in manifest['sites']:
                    row=con.execute('SELECT uri,category,kind FROM sites WHERE id=?',(int(site['site_id'][1:]),)).fetchone()
                    metadata_mapping = False
                    if row and manifest.get('classification_metadata_version') == 'source-category-1':
                        from .react_protocol import VERSION
                        for (material,) in con.execute('SELECT t.task_json FROM m4_attempts a JOIN m4_tasks t ON a.task_key=t.task_key WHERE a.site_id=? AND a.batch_id=?', (site['site_id'],manifest['batch_id'])):
                            task=json.loads(material)
                            uri=(task.get('pilot_identity') or {}).get('application',{}).get('canonical_uri') or task['site_uri']
                            if (task.get('fragment',{}).get('decision_protocol') == VERSION
                                    and task['site_category'] == site['site_category'] and uri == site['uri']):
                                metadata_mapping=True
                                break
                    if (not row or row[0]!=site['uri'] or row[2]!='real' or
                            row[1]!=site['site_category'] and not metadata_mapping):
                        raise ValueError('账本与既有站点映射不一致：'+site['site_id'])
                for sample_id in manifest['samples']:
                    row=con.execute('SELECT batch_id FROM allocations WHERE sample_id=?',(sample_id,)).fetchone()
                    if row!=(manifest['batch_id'],):raise ValueError('账本与既有样本批次不一致：'+sample_id)
    except (sqlite3.Error,OSError,KeyError,TypeError,ValueError) as e:
        raise ValueError('编号账本核对失败：'+str(e)) from e
