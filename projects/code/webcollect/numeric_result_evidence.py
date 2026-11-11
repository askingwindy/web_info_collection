"""Small, versioned comparison of single observed result numbers.

This does not calculate answers or identify result areas. The caller must retain
its synchronized page/region binding and exclude input echoes.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import unicodedata

VERSION = 'numeric-result-evidence'
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
    # A displayed variable assignment is an explicit result, not a field-label
    # alias. Preserve the variable identity and compare only its stated number.
    assignments=[re.fullmatch(r'([A-Za-z])=([-+]?\d+(?:\.\d+)?)',normalized(v)) for v in (expected,observed)]
    if all(assignments) and assignments[0].group(1)==assignments[1].group(1):
        target,actual=(_parse(m.group(2),'') for m in assignments)
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
    return {'policy': VERSION, 'observed_visible_text': str(observed),
            'expected_visible_text': str(expected),
            'comparison': 'rounded_to_explicit_approximate_precision' if got != wanted else 'normalized_exact'}


def substantive_result_text(value, *, field="", numeric=True):
    """A label is not an answer, even inside a genuine submitted result area.

    numeric=False keeps the label/weak-text filtering but accepts a text-only
    endpoint; its causality is then checked separately (result execution
    binding), not by the digit rule used for numeric answers.
    """
    text=normalized(value)
    label=normalized(field).rstrip(":：")
    if not text or weak_result_text(text) or text.rstrip(":：") == label:
        return False
    # Result labels commonly end in a colon while their value is a sibling.
    if text.endswith((":", "：")) or numeric and not re.search(r"[0-9]",text):
        return False
    return True


def process_field(field):
    return bool(re.search(r"(?:逐步|分步|求解|计算|計算).*(?:过程|過程|步骤|步驟)",str(field)))


def process_result_text(value, field):
    """Recognize explicit algebra steps, without deriving any answer."""
    if not process_field(field):
        return False
    text=unicodedata.normalize('NFKC',str(value))
    return (len(re.findall(r"=\s*[-+]?\d",text)) >= 2
            and len(re.findall(r"Subtract|Divide|Multiply|Add|减去|減去|除以|乘以|加上",text,re.I)) >= 2)
