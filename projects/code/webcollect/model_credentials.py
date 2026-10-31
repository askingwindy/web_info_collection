"""Runtime-only model credentials; never return them in configuration or logs."""
import os
import random
import re
from pathlib import Path


# The user authorized this project's ignored request/token as its GLM source.
# Source checkouts resolve it without storing a machine-specific absolute path.
PROJECT_GLM_TOKEN = Path(__file__).resolve().parents[3] / 'request' / 'token'
PROJECT_GLM_YAML = PROJECT_GLM_TOKEN.with_name('token.yaml')
PROJECT_GLM_ACCOUNT = 'glm'


def _glm_session_key(account_keys):
    """One uniform random pick per session; kept for the whole session.

    2026-10-30 user authorization: the glm account list holds several equally
    authorized keys; each ModelGateway (one planning-collection trajectory)
    selects one when it starts. A failing key is never rotated mid-session —
    the failure is recorded in the original ledger like any other.
    """
    if not account_keys:
        raise ValueError('Empty credential account list')
    return random.SystemRandom().choice(account_keys)


def _yaml_account(path, account):
    import yaml
    class UniqueLoader(yaml.SafeLoader):
        pass
    def mapping(loader,node):
        result={}
        for key_node,value_node in node.value:
            key=loader.construct_object(key_node)
            if key in result:raise ValueError('Duplicate credential account')
            result[key]=loader.construct_object(value_node)
        return result
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
    try:
        with Path(path).open('r',encoding='utf-8-sig') as stream:material=stream.read(65537)
        if len(material)>65536:raise ValueError('Oversize credentials')
        material='\n'.join(line[:len(line)-len(line.lstrip(' \t'))].expandtabs(2)+line.lstrip(' \t')
                           for line in material.splitlines())
        try:
            accounts=yaml.load(material,Loader=UniqueLoader)
        except yaml.YAMLError:
            # The authorized file can retain legacy account labels after being
            # renamed .yaml. Read only an explicit top-level ark1 token; never
            # guess a key from malformed YAML or use the GLM account instead.
            if account != 'ark1' or not re.search(r'(?m)^ark1[ \t]*[:：=]', material):
                raise
            value=_ark_value(material)
        else:
            value=accounts[account]
            if account=='glm' and isinstance(value,list):
                value=_glm_session_key(value)
            if isinstance(value,dict):value=value['api_key']
        if not isinstance(value,str):raise ValueError('String account key required')
        return value.strip()
    except (OSError,UnicodeError,yaml.YAMLError,ValueError,TypeError,KeyError,IndexError):
        raise ValueError('Selected YAML credential account unavailable or ambiguous; secret content suppressed') from None
PROJECT_ARK_TOKEN = PROJECT_GLM_TOKEN


def _ark_value(value):
    """Select only the user's ark1 entry in a shared labelled token file."""
    entries = re.findall(r'(?im)^[ \t]*ark1[ \t]*[:：=][ \t]*(?:\r?\n[ \t]*)?([A-Za-z0-9_.-]+)[ \t]*$', value)
    labels = re.findall(r'(?im)^[ \t]*ark1[ \t]*[:：=]', value)
    if labels:
        if len(entries) != 1 or len(labels) != 1:
            raise ValueError('Model credential ark1 entry ambiguous; secret content suppressed')
        return entries[0]
    return value  # A dedicated ark1 file or environment variable is one token.


def credential(model):
    value = os.environ.get(model['api_key_env'])
    if not value:
        source = model.get('api_key_file')
        if source is None and model['provider'] == 'glm':
            source = PROJECT_GLM_YAML if PROJECT_GLM_YAML.is_file() else PROJECT_GLM_TOKEN
        if source is None and model['provider'] == 'ark':
            source = PROJECT_ARK_TOKEN
        if source is None:
            raise ValueError('Missing model credential environment: ' + model['api_key_env'])
        try:
            if model['provider'] == 'ark' and Path(source).is_dir():
                source = Path(source) / 'ark1'
            if Path(source).suffix.lower() in ('.yaml','.yml'):
                account = 'ark1' if model['provider'] == 'ark' else PROJECT_GLM_ACCOUNT
                value=_yaml_account(source,account)
            else:
                with Path(source).open('r', encoding='utf-8') as stream:
                    value = stream.read(4097).strip()
        except (OSError, UnicodeError):
            raise ValueError('Model credential file unavailable; secret content suppressed') from None
        if len(value) > 4096:
            raise ValueError('Model credential file too large; secret content suppressed')
        if model['provider'] == 'ark':
            value = _ark_value(value)
        if model['provider'] == 'glm' and any(not 33 <= ord(char) <= 126 for char in value):
            # The authorized local file may include a Chinese label. Accept
            # exactly one GLM id.secret token, never guess among credentials.
            candidates = set(re.findall(r'(?<![A-Za-z0-9_.-])[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_.-])', value))
            if len(candidates) == 1:
                value = candidates.pop()
    # A plain single token is required; errors never echo the token or file text.
    if (not value or len(value) > 4096 or value.startswith(('{', '['))
            or any(not 33 <= ord(char) <= 126 for char in value)):
        raise ValueError('Model credential must be a single bounded token; secret content suppressed')
    return value
