"""Translations for application-owned messages, never user data or model answers."""
import json
import re
from pathlib import Path

ENGLISH = json.loads((Path(__file__).parent / 'locales' / 'en.json').read_text(encoding='utf-8'))
LANGUAGES = ('zh-CN', 'en-US')


def translate(text, language='zh-CN'):
    if language != 'en-US' or not isinstance(text, str):
        return text
    if text in ENGLISH:
        return ENGLISH[text]
    # Translate only catalogued templates, preserving interpolated values.
    for template, english in ENGLISH.items():
        if '{0}' not in template:
            continue
        pattern = re.escape(template)
        pattern = re.sub(r'\\\{\d+\\\}', '(.*?)', pattern)
        match = re.fullmatch(pattern, text, re.DOTALL)
        if match:
            return english.format(*(translate(value, language) for value in match.groups()))
    if text.startswith('Value error, '):
        return translate(text[len('Value error, '):], language)
    return text
