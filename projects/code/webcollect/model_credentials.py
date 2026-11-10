"""Runtime-only model credentials; never return them in configuration or logs."""
import hashlib
import secrets
import os
import re
from pathlib import Path


# The user authorized this project's ignored request/token as its GLM source.
# Source checkouts resolve it without storing a machine-specific absolute path.
PROJECT_GLM_TOKEN = Path(__file__).resolve().parents[3] / 'request' / 'token'
PROJECT_GLM_YAML = PROJECT_GLM_TOKEN.with_name('token.yaml')
PROJECT_GLM_ACCOUNT = 'glm'


def account_id(value):
    """Opaque, non-secret identity used only for local account scheduling."""
    return 'glm-' + hashlib.sha256(value.encode()).hexdigest()


def _glm_session_key(account_keys, excluded_accounts=(), required_account=None, selection_index=0):
    """Use random selection when requested; recover an existing account by identity."""
    available = []
    seen = set()
    for entry in account_keys:
        key = entry.get('api_key') if isinstance(entry, dict) else entry
        if not isinstance(key, str) or not key.strip() or len(key.strip()) > 4096 or any(not 33 <= ord(c) <= 126 for c in key.strip()):
            raise ValueError('String account key required')
        key = key.strip()
        identity = account_id(key)
        if identity not in excluded_accounts and key not in seen:
            available.append(key)
            seen.add(key)
    account_keys = available
    if not account_keys:
        raise ValueError('No authorized credential account available; reconcile original account hold')
    if required_account is not None:
        for key in account_keys:
            if account_id(key) == required_account:
                return key
        raise ValueError('Original credential account unavailable; no replacement selection')
    return secrets.choice(account_keys) if selection_index is None else account_keys[selection_index % len(account_keys)]


def _yaml_account(path, account, excluded_accounts=(), required_account=None, selection_index=0):
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
                value=_glm_session_key(value, excluded_accounts, required_account, selection_index)
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


def credential(model, *, excluded_accounts=(), required_account=None, selection_index=0):
    explicit_yaml = model.get('api_key_file') and Path(model['api_key_file']).suffix.lower() in ('.yaml', '.yml')
    value = None if explicit_yaml and model['provider'] == 'glm' else os.environ.get(model['api_key_env'])
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
                value=_yaml_account(source,account,excluded_accounts,required_account,selection_index)
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
    if model['provider'] == 'glm' and account_id(value) in excluded_accounts:
        raise ValueError('Selected authorized account is held in original ledger')
    if required_account is not None and account_id(value) != required_account:
        raise ValueError('Original credential account unavailable; secret content suppressed')
    return value


def configured_credentials(model):
    """Enumerate runtime secrets without exposing them in configuration or evidence."""
    excluded = set()
    while True:
        try:
            secret = credential(model, excluded_accounts=excluded)
        except ValueError:
            if not excluded:
                raise
            return
        identity = account_id(secret)
        if identity in excluded:
            return
        excluded.add(identity)
        yield identity, secret
