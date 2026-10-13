"""Local, versioned lexical retrieval. No embedding service or training required."""
import math
import re
from collections import Counter


def tokens(text):
    text = text.lower()
    words = re.findall(r'[a-z0-9_]+', text)
    for span in re.findall(r'[\u4e00-\u9fff]+', text):
        words.extend(span[i:i + 2] for i in range(max(1, len(span) - 1)))
    return words


def bm25_scores(texts, question):
    bags = [Counter(tokens(text)) for text in texts]
    average = sum(sum(b.values()) for b in bags) / max(1, len(bags)) or 1
    query = set(tokens(question))
    frequencies = {term: sum(term in b for b in bags) for term in query}
    return [sum(math.log(1 + (len(bags)-frequencies[term]+.5)/(frequencies[term]+.5)) * bag[term]*2.2 /
                (bag[term]+1.2*(.25+.75*sum(bag.values())/average)) for term in query) for bag in bags]


def retrieve(context, question, limit=8):
    """Rank overlapping paragraph chunks with BM25; keep governance notes separately.

    The caller also supplies the full confirmed context as a constraint envelope:
    retrieval must never hide exclusions or a conflicting metric definition.
    """
    documents = []
    for section in ('notes', 'fields', 'metrics', 'relationships'):
        content = context.get(section, '')
        for start in range(0, len(content), 600):
            text = content[start:start + 800]
            documents.append({'id': f'{section}:{start}@v{context["version"]}',
                              'section': section, 'version': context['version'],
                              'text': text, 'offset': start})
    if not documents:
        return []
    for doc, score in zip(documents, bm25_scores([d['text'] for d in documents], question)):
        doc['score'] = round(score, 5)
    return sorted((d for d in documents if d['score'] > 0), key=lambda d: (-d['score'], d['id']))[:limit]


def evidence(result):
    """Profile all returned rows; never call a capped result the full database."""
    rows = result['rows']
    numeric = {}
    for i, column in enumerate(result['columns']):
        values = [r[i] for r in rows if isinstance(r[i], (int, float)) and not isinstance(r[i], bool)]
        if values:
            numeric[column] = {'count': len(values), 'sum': round(sum(values), 6),
                               'min': min(values), 'max': max(values)}
    return {key: result.get(key) for key in ('sql', 'columns', 'row_count', 'truncated')} | {
        'rows': rows[:30], 'sample_row_count': min(30, len(rows)),
        'returned_rows_profile': numeric,
        'scope': 'Profiles cover ALL RETURNED rows only. SQL LIMIT and engine truncation may exclude records. '
                 'The sample is at most 30 rows. Column sums are mechanical, not necessarily meaningful '
                 '(never sum IDs, rates, averages or cumulative totals). Run aggregate SQL for population claims.'}
