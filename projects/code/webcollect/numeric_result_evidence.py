"""Small, versioned comparison of single observed result numbers.

This does not calculate answers or identify result areas. The caller must retain
its synchronized page/region binding and exclude input echoes.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import unicodedata

VERSION = 'webcollect-numeric-result-evidence-1'
_NUMBER = re.compile(r'(?<![\d.,])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\d.,])')
_UNITS = {'%':'percent', '百分比':'percent', '百分之':'percent',
          '元':'cny', '人民币':'cny', '人民币元':'cny', 'CNY':'cny', 'RMB':'cny', '¥':'cny',
          '美元':'usd', 'USD':'usd', '$':'usd',
          '千克':'kg', '公斤':'kg', 'kg':'kg', '克':'g', 'g':'g'}
_WEAK = {'$', '¥', '%', '结果', '计算结果', 'result', 'output'}


def normalized(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or '')))


def weak_result_text(value):
    return normalized(value).casefold() in _WEAK


def _parse(value, field):
    value = normalized(value)
    hits = list(_NUMBER.finditer(value))
    if len(hits) != 1:
        return None
    hit = hits[0]
    before, after = value[:hit.start()], value[hit.end():]
    approximate = bool(re.search(r'约|大约|≈|~', before))
    before = re.sub(r'大约|约|≈|~', '', before)
    # Only the already bound field label may accompany a number. Arbitrary
    # prose (FAQ, input captions, unknown units) is never interpreted.
    label = normalized(field)
    for punctuation in (':', '=', '为', '是'):
        before = before.rstrip(punctuation)
    if label and before.startswith(label):
        before = before[len(label):].lstrip(':=').removeprefix('为').removeprefix('是')
    unit_text = before + after
    unit = _UNITS.get(unit_text) if unit_text else ''
    if unit is None:
        return None
    raw = hit.group().replace(',', '')
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    return number, unit, len(raw.split('.')[1]) if '.' in raw else 0, approximate


def numeric_target(value, field=""):
    return _parse(value, field) is not None


def match_result(expected, observed, *, field, result_bound, input_node=False):
    """Return evidence metadata only for a bound, unambiguous result match."""
    if not result_bound or input_node or weak_result_text(expected):
        return None
    target, actual = _parse(expected, field), _parse(observed, field)
    if target is None or actual is None:
        return None
    wanted, unit, precision, approximate = target
    got, observed_unit, _, _ = actual
    # Explicit unit aliases only; absent units do not inherit a guessed unit.
    if unit != observed_unit:
        return None
    if got != wanted:
        if not approximate:
            return None
        quantum = Decimal(1).scaleb(-precision)
        try:
            rounded = got.quantize(quantum, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return None
        if rounded != wanted:
            return None
    return {'protocol': VERSION, 'observed_visible_text': str(observed),
            'expected_visible_text': str(expected),
            'comparison': 'rounded_to_explicit_approximate_precision' if got != wanted else 'normalized_exact'}
