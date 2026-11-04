"""Customer site parents, independent of producer-only engineering categories."""
from collections import Counter


# Requirement section 5, interpreted by the 2026-11-02 coverage clarification.
# Keep the original labels visible; never infer a site's category from its URI
# or from the purpose of one page. 知识文库 is allowed, but is not required.
REQUIRED_CATEGORIES = {
    '百科与文档站': '百科与文档',
    '新闻资讯': '新闻资讯',
    '企业后台与开源演示站': '企业后台与开源演示站',
    '在线工具': '在线工具',
    '开发者站与 API 文档': '开发者站与 API 文档',
    '学习教育': '学习教育',
    '政务与公共服务查询': '政务与公共服务查询',
    '图书影音榜单': '图书文化',
    '电商浏览': '电商浏览',
    '交通出行查询': '交通出行查询',
    '医疗健康科普': '健康科普',
    '招聘房产分类信息': '招聘房产分类信息',
    '小游戏': '小游戏',
    '金融股票交易': '金融股票交易',
}
ALIASES = {**REQUIRED_CATEGORIES, '开发者站与API文档': '开发者站与 API 文档'}
POLICY = {'version': 'formal-corpus-site-category-coverage-1',
          'required_categories': REQUIRED_CATEGORIES, 'aliases': ALIASES,
          'scope': 'release.kind == formal; explicit effective corpus only',
          'parent_distribution_policy': 'canonical-site-parent-shares-1',
          'parent_distribution_scopes': ['delivery-profile', 'quality-batch', 'cumulative'],
          'minimum_share_per_required_category': None,
          'sources': ['requirement section 5', 'site_trajectory_scope 2026-11-02']}


def parent_category(value):
    value = value.strip() if isinstance(value, str) else ''
    return ALIASES.get(value, value)


def category_coverage(categories, configuration):
    """Counts are supplied only for source-mapped, selected effective samples."""
    counts = Counter()
    for label, count in categories.items():
        counts[parent_category(label)] += count
    required = list(REQUIRED_CATEGORIES.values())
    present = [label for label in required if counts[label] > 0]
    missing = [label for label in required if counts[label] <= 0]
    enforced = configuration.get('release', {}).get('kind') == 'formal'
    return {'status': ('FAIL' if missing else 'PASS') if enforced else 'NOT_APPLICABLE',
            'enforced': enforced, 'policy_version': POLICY['version'],
            'required': required, 'present': present, 'missing': missing,
            'sample_counts': {label: counts[label] for label in required},
            'other_category_counts': {label: count for label, count in counts.items() if label not in required},
            'requirement_to_parent': dict(REQUIRED_CATEGORIES),
            'basis': 'source-mapped explicit effective sample versions; no page/URI inference'}
