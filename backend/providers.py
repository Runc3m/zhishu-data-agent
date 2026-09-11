"""Provider presets keep routine setup down to one API key."""
from urllib.parse import urlparse

DEEPSEEK_URL = 'https://api.deepseek.com'
DEEPSEEK_MODEL = 'deepseek-v4-flash'


def provider_settings(data):
    data = dict(data)
    if not data.get('provider'):
        host = urlparse(data.get('base_url', DEEPSEEK_URL)).hostname
        data['provider'] = 'deepseek' if host == 'api.deepseek.com' else 'custom'
    if data['provider'] == 'deepseek':
        data.update(base_url=DEEPSEEK_URL, model=DEEPSEEK_MODEL)
    return data
