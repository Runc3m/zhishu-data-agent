"""Keep public documentation links and paired translations usable."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_document_links():
    for document in list(ROOT.glob('*.md')) + list((ROOT / 'docs').rglob('*.md')):
        for target in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
            if target.startswith(('https://', 'http://', '#')):
                continue
            assert (document.parent / target.split('#')[0]).exists(), (document.name, target)


def test_bilingual_document_pairs():
    for topic in ('usage', 'models', 'development', 'faq', 'roadmap'):
        for language in ('zh-CN', 'en'):
            assert (ROOT / f'docs/{topic}.{language}.md').stat().st_size > 200
    for topic in ('README', 'CONTRIBUTING', 'CHANGELOG'):
        assert (ROOT / f'{topic}.md').exists()
        assert (ROOT / f'{topic}.en.md').exists()
