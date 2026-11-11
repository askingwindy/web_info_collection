"""Offline, ordered selection from frozen discovery evidence; never grants ready.

No URL is fetched or invented. Link labels and URL shapes are only routing cues:
selected pages still need rendered capability evidence and review. Catalogs are
deliberately not accepted as selection inputs.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

VERSION = 'frozen-link-selection'
RULE_SCHEMA = 'candidate-selection-rules'
# Old rules files were stamped with the generational value; reads accept both.
PREVIOUS_RULE_SCHEMA = 'webcollect-candidate-selection-rules-1'


def default_rules():
    """Host-independent ordered cues, frozen verbatim alongside every result."""
    return {
        'schema_version': RULE_SCHEMA,
        'max_selected': None,
        'max_selected_per_source': None,
        'rules': [
            {'id': 'fragment_navigation', 'class': 'navigation', 'field': 'href',
             'pattern': r'^\s*#', 'select': False},
            {'id': 'api_documentation', 'class': 'api_document', 'field': 'path',
             'pattern': r'(^|/)(api|docs?|documentation)(/|$)|documentation|openapi', 'select': False},
            {'id': 'article_or_tutorial', 'class': 'article', 'field': 'path',
             'pattern': r'(^|/)(article|articles|blog|blogs|news|tutorials?)(/|$)', 'select': False},
            {'id': 'entry_page', 'class': 'entry', 'field': 'path',
             'pattern': r'^/(?:[a-z]{2}(?:_[a-z]{2})?/)?(?:index(?:\.html?)?)?/?$', 'select': False},
            {'id': 'account_navigation', 'class': 'navigation', 'field': 'path',
             'pattern': r'(^|/)(login|logout|register|signup|contact|about|download)(/|$)', 'select': False},
            {'id': 'category_navigation', 'class': 'navigation', 'field': 'path',
             'pattern': r'(^|/)(class|category|categories|tags?|channels?)(/|$)|-sites/?$', 'select': False},
            {'id': 'label_navigation', 'class': 'navigation', 'field': 'text',
             'pattern': r'导航|频道|工具箱|更多频道|^(首页|文库|联系方式|简体中文|繁體中文|站点地图)$', 'select': False},
            {'id': 'non_page_asset', 'class': 'non_page', 'field': 'path',
             'pattern': r'\.(?:xml|zip|pdf|png|jpe?g|gif|svg|js|css|mp[34])$', 'select': False},
            {'id': 'specific_tool_path', 'class': 'functional_candidate', 'field': 'path',
             'pattern': r'^/(?:front-end|compile|more|string|convert|encrypt|coordinate|math|network|image|common)/[^/]+/?$', 'select': True},
            {'id': 'functional_label', 'class': 'functional_candidate', 'field': 'text',
             'pattern': r'计算器|转换器?|格式化|编译|在线(?:测试|画图|编辑)|计时器|倒计时|随机(?:数|密码)|二维码(?:生成|识别)|代码(?:运行|预览)', 'select': True},
        ],
    }


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def _object_sha(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _load(path):
    return json.loads(Path(path).read_text())


def _normalize_uri(value):
    p = urlsplit(value)
    host = (p.hostname or '').lower().rstrip('.')
    if p.scheme.lower() not in ('http', 'https') or not host or p.username or p.password:
        raise ValueError('not an uncredentialed HTTP(S) link')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.invalid')):
        raise ValueError('local/test host')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError('non-public IP address')
    host = host.encode('idna').decode()
    port = p.port
    host = '[' + host + ']' if ':' in host else host
    netloc = host if port is None or (p.scheme.lower(), port) in (('http', 80), ('https', 443)) else host + ':' + str(port)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith('utm_')]
    return urlunsplit((p.scheme.lower(), netloc, p.path or '/', urlencode(sorted(query)), ''))


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.current = None
            if attrs.get('href'):
                self.current = {'href': attrs['href'], 'text': '', 'title': attrs.get('title', '')}
                self.links.append(self.current)
        elif tag == 'img' and self.current is not None and attrs.get('alt'):
            self.current['text'] += ' ' + attrs['alt']

    def handle_endtag(self, tag):
        if tag == 'a':
            self.current = None

    def handle_data(self, data):
        if self.current is not None:
            self.current['text'] += data


def _validated_rules(value):
    value = deepcopy(value)
    if value.get('schema_version') not in (RULE_SCHEMA, PREVIOUS_RULE_SCHEMA):
        raise ValueError('versioned candidate selection rules required')
    for key in ('max_selected', 'max_selected_per_source'):
        if value.get(key) is not None and (type(value[key]) is not int or value[key] < 1):
            raise ValueError(key + ' must be a positive integer')
    if not isinstance(value.get('rules'), list) or not value['rules']:
        raise ValueError('at least one explicit selection rule required')
    ids = set()
    classes = {'navigation', 'entry', 'api_document', 'article', 'non_page', 'functional_candidate'}
    for rule in value['rules']:
        if not isinstance(rule.get('id'), str) or not rule['id'] or rule['id'] in ids:
            raise ValueError('rule ids must be nonempty and unique')
        ids.add(rule['id'])
        if rule.get('field') not in ('href', 'path', 'text') or rule.get('class') not in classes:
            raise ValueError('unsupported rule field/class')
        if type(rule.get('select')) is not bool or (rule['select'] and rule['class'] != 'functional_candidate'):
            raise ValueError('only functional_candidate rules may select links')
        re.compile(rule['pattern'], re.IGNORECASE)
    return value


def _classify(link, uri, rules):
    values = {'href': link['href'], 'path': urlsplit(uri).path, 'text': link['text']}
    for rule in rules['rules']:
        if re.search(rule['pattern'], values[rule['field']], re.IGNORECASE):
            return rule['class'], rule['id'], rule['select']
    return 'unknown', 'no_functional_cue', False


def select_candidates(supply_paths, output, rules=None):
    """Write a new immutable selection, retaining every observed link occurrence.

    Missing raw HTML never falls back to a chosen subset: its denominator remains
    unknown. The original candidates/deferred/reject sets are copied verbatim as
    provenance, so their failures and prior choices remain inspectable.
    """
    rules = _validated_rules(default_rules() if rules is None else rules)
    paths = [Path(p).resolve() for p in supply_paths]
    output = Path(output).resolve()
    if not paths or len(set(paths)) != len(paths):
        raise ValueError('distinct frozen supply directories required')
    if output.exists():
        raise FileExistsError('refuse to overwrite an existing selection: ' + str(output))
    if any(output == p or p in output.parents for p in paths):
        raise ValueError('new selection must be outside all frozen supply directories')
    inputs, original, source_rows, rows, records = {}, [], [], [], {}
    modes = set()
    for supply_index, base in enumerate(paths):
        candidate_path, sources_path = base / 'candidates.json', base / 'sources-frozen.json'
        candidates, sources = _load(candidate_path), _load(sources_path)
        # Sealed historical exports carry the old generational schema names; both read.
        if (candidates.get('schema_version') not in ('site-candidates', 'webcollect-site-candidates-1')
                or sources.get('schema_version') not in ('site-sources', 'webcollect-site-sources-1')):
            raise ValueError('frozen discovery candidates and sources required')
        modes.add(candidates.get('mode'))
        for path in (candidate_path, sources_path):
            inputs[str(path)] = _sha(path)
        original.append({'supply': str(base), 'candidates': candidates, 'sources': sources})
        previous = {r['site_uri'] for r in candidates['records']}
        deferred = {r['uri'] for r in candidates.get('deferred_links', [])}
        observed = 0
        for source_index, source in enumerate(sources['sources']):
            ref = {'supply_index': supply_index, 'source_index': source_index, 'supply': str(base),
                   'kind': source.get('kind'), 'category': source.get('category'),
                   'source_config': source, 'source_sha256': inputs[str(sources_path)],
                   # Preserve the legacy alias; neither field is an HTML/content hash.
                   'sources_sha256': inputs[str(sources_path)]}
            unavailable = None
            if source.get('kind') == 'seed':
                links = [{'href': uri, 'text': '', 'title': ''} for uri in source.get('uris', [])]
                base_uri, source_file = None, sources_path
            else:
                source_file = base / ('source-' + str(source_index) + '.json')
                if not source_file.exists():
                    failure = base / ('source-failure-' + str(source_index) + '.json')
                    unavailable = {'reason': 'frozen raw source HTML unavailable', 'link_occurrences': 'UNKNOWN'}
                    if failure.exists():
                        inputs[str(failure)] = _sha(failure)
                        unavailable['source_failure'] = _load(failure)
                    links, base_uri = [], None
                else:
                    raw = _load(source_file)
                    parser = _Links()
                    parser.feed(raw['html'])
                    parser.close()
                    links, base_uri = parser.links, raw['landed_uri']
            if source_file.exists():
                inputs[str(source_file)] = _sha(source_file)
                ref.update(source_file=str(source_file), source_file_sha256=inputs[str(source_file)])
            ref['landed_uri'] = base_uri
            selected_here = 0
            for link_index, link in enumerate(links, 1):
                observed += 1
                text = ' '.join(link['text'].split())
                row = {'occurrence': len(rows) + 1, 'source_link_index': link_index,
                       'source': ref, 'raw_href': link['href'], 'anchor_text': text,
                       'anchor_title': link['title'], 'selected': False, 'eligible': False}
                resolved = urljoin(base_uri, link['href']) if base_uri else link['href']
                row['resolved_uri'] = resolved
                try:
                    uri = _normalize_uri(resolved)
                except (ValueError, UnicodeError) as error:
                    row.update(classification='invalid', reason='invalid_public_uri', detail=str(error))
                    rows.append(row)
                    continue
                row.update(uri=uri, prior_selected=uri in previous, prior_deferred=uri in deferred)
                classification, rule_id, eligible = _classify({**link, 'text': text}, uri, rules)
                row.update(classification=classification, matched_rule=rule_id, eligible=eligible, reason=rule_id)
                if source.get('allowed_domains') and urlsplit(uri).hostname not in source['allowed_domains']:
                    row.update(eligible=False, reason='outside_frozen_source_domain_scope')
                if row['eligible']:
                    if uri in records:
                        row.update(reason='duplicate_selected_uri', duplicate_of=records[uri]['selection_occurrence'])
                        if ref not in records[uri]['source']:
                            records[uri]['source'].append(ref)
                    elif rules.get('max_selected_per_source') is not None and selected_here >= rules['max_selected_per_source']:
                        row['reason'] = 'selection_per_source_limit'
                    elif rules.get('max_selected') is not None and len(records) >= rules['max_selected']:
                        row['reason'] = 'selection_global_limit'
                    else:
                        row.update(selected=True, reason='selected_functional_cue')
                        records[uri] = {'site_uri': uri, 'site_category': source.get('category', 'UNKNOWN'),
                            'source': [ref], 'selection_occurrence': row['occurrence'],
                            'selection_rule': rule_id, 'status': 'not_probed', 'ready': False,
                            'selection_class': 'functional_candidate', 'real_supply_verified': False}
                        selected_here += 1
                rows.append(row)
            source_rows.append({**ref, 'link_occurrences': 'UNKNOWN' if unavailable else len(links),
                                'selected_new_uris': selected_here, 'unavailable': unavailable})
        declared = candidates.get('discovery_link_occurrences')
        if type(declared) is int and observed != declared:
            raise ValueError('reconstructed link count does not match frozen discovery denominator: '
                             + str(base) + ' (' + str(observed) + ' != ' + str(declared) + ')')
    if len(modes) != 1 or next(iter(modes)) not in ('real', 'synthetic'):
        raise ValueError('all discovery inputs must use the same real/synthetic mode')
    if any(_sha(path) != digest for path, digest in inputs.items()):
        raise ValueError('frozen selection input changed while reading')
    implementation_sha = _sha(__file__)
    fingerprint = _object_sha({'inputs': inputs, 'rules': rules, 'version': VERSION,
                               'implementation_sha256': implementation_sha})
    candidates = {'schema_version': 'site-candidates', 'version': VERSION,
        'mode': next(iter(modes)), 'input_source_sha256': fingerprint,
        'records': list(records.values()), 'fixed_candidate_count': len(records),
        'discovery_link_occurrences': len(rows), 'link_denominator_complete': all(not r['unavailable'] for r in source_rows),
        'independent_host_count': len({urlsplit(uri).hostname for uri in records}),
        'sample_ids_allocated': 0, 'real_supply_verified': False,
        'selection_status': 'mechanical_candidates_only', 'rules_sha256': _object_sha(rules),
        'selection_evidence': str(output / 'selection-evidence.json')}
    summary = {'schema_version': 'webcollect-candidate-selection-summary-1', 'version': VERSION,
        'selection_sha256': fingerprint, 'input_files_sha256': inputs, 'rules_sha256': _object_sha(rules),
        'implementation_sha256': implementation_sha,
        'observed_link_occurrences': len(rows), 'total_source_link_denominator': len(rows) if candidates['link_denominator_complete'] else 'UNKNOWN',
        'source_count': len(source_rows), 'sources_without_raw_link_denominator': sum(bool(r['unavailable']) for r in source_rows),
        'recorded_source_failures': sum(bool(r['unavailable'] and r['unavailable'].get('source_failure')) for r in source_rows),
        'normalized_unique_uris': len({r['uri'] for r in rows if r.get('uri')}),
        'classification_counts': dict(Counter(r['classification'] for r in rows)),
        'decision_counts': dict(Counter(r['reason'] for r in rows)),
        'eligible_occurrences': sum(r['eligible'] for r in rows),
        'eligible_unique_uris': len({r['uri'] for r in rows if r['eligible']}), 'selected_unique_uris': len(records),
        'selected_from_prior_deferred': sum(r['selected'] and r.get('prior_deferred', False) for r in rows),
        'independent_host_count': candidates['independent_host_count'], 'ready_count': 0,
        'new_network_requests': 0, 'new_model_requests': 0, 'external_model_cost': 0,
        'development_session_infrastructure_cost': 'UNKNOWN', 'real_qualified_samples': 0,
        'limits': ['URL/text cues do not prove visible functionality, Chinese content, natural task length, free access, or task diversity.',
                   'Original source failures retain UNKNOWN link denominators; no replacement sources were fetched.',
                   'Links are deduplicated by normalized URI, not by independent website or business task.',
                   'Catalogs and prior successful outcomes were not used to select or rank links.'],
        'candidate_file': str(output / 'candidates.json')}
    output.mkdir(parents=True, exist_ok=False)
    files = {'rules-frozen.json': rules, 'original-discovery.json': original,
             'selection-evidence.json': {'sources': source_rows, 'occurrences': rows},
             'candidates.json': candidates, 'summary.json': summary}
    for name, value in files.items():
        with (output / name).open('xb') as stream:
            stream.write(_encoded(value))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--supply', action='append', type=Path, help='Frozen discovery directory; repeat to preserve source order')
    parser.add_argument('--rules', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--print-default-rules', action='store_true')
    args = parser.parse_args(argv)
    if args.print_default_rules:
        print(_encoded(default_rules()).decode(), end='')
        return 0
    if not args.supply or not args.output:
        parser.error('--supply and --output are required')
    try:
        result = select_candidates(args.supply, args.output, _load(args.rules) if args.rules else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, re.error) as error:
        print(json.dumps({'status': 'STOP', 'reason': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
