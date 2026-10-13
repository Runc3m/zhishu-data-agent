"""Versioned business retrieval using FastEmbed/ONNX + BM25/RRF.

Embeddings are optional and local-only at request time. Download/setup is explicit;
network access and model code execution are never delegated to document content.
"""
import hashlib
import json
import os
import re
import threading
from pathlib import Path

from .knowledge import bm25_scores

MODEL_ID = 'intfloat/multilingual-e5-small'
MODEL_PATH = Path(__file__).resolve().parents[1] / 'storage' / 'models' / 'multilingual-e5-small'
_lock = threading.RLock()
_model = None
_cache = {}


def model():
    global _model
    if not MODEL_PATH.is_dir() or os.environ.get('INSIGHTBRIDGE_LEXICAL_ONLY') == '1':
        return None
    with _lock:
        if _model is None:
            from fastembed import TextEmbedding
            from fastembed.common.model_description import ModelSource, PoolingType
            if MODEL_ID not in {m['model'] for m in TextEmbedding.list_supported_models()}:
                TextEmbedding.add_custom_model(model=MODEL_ID, pooling=PoolingType.MEAN,
                    normalization=True, sources=ModelSource(hf=MODEL_ID), dim=384,
                    model_file='onnx/model.onnx', license='MIT', size_in_gb=.47)
            _model = TextEmbedding(model_name=MODEL_ID, specific_model_path=str(MODEL_PATH),
                                   threads=2, providers=['CPUExecutionProvider'], local_files_only=True)
        return _model


def documents(context, source):
    docs = []
    for section in ('notes', 'fields', 'metrics', 'relationships'):
        # Split at sentence boundaries; preserve whole definitions up to model token limit.
        parts = re.split(r'\n\s*\n|(?<=[。.;])\s+(?=[A-Z\u4e00-\u9fff])', context.get(section, ''))
        for i, part in enumerate(parts):
            for j in range(0, len(part), 600):
                text = part[j:j+800].strip()
                if text:
                    docs.append({'id': f'{section}:{i}:{j}@v{context["version"]}', 'section': section,
                                 'text': text, 'version': context['version'], 'source_id': source['id']})
    for table in source['tables']:
        docs.append({'id': 'schema:' + table['name'], 'section': 'schema', 'version': context['version'],
                     'source_id': source['id'], 'text': json.dumps(table, ensure_ascii=False)})
    for step in source.get('pipeline', []):
        docs.append({'id': 'etl:' + step['table'], 'section': 'etl', 'version': step['version'],
                     'source_id': source['id'], 'text': json.dumps(step, ensure_ascii=False)})
    # Imported registry belongs to its original confirmed context. An edited
    # context must not silently inherit a stale structured formula.
    metrics = source.get('metrics', []) if context['version'] == source.get('metrics_context_version', 1) else []
    for metric in metrics:
        docs.append({'id': 'metric:' + metric['id'], 'section': 'metric', 'version': context['version'],
                     'source_id': source['id'], 'text': json.dumps(metric, ensure_ascii=False)})
    return docs


def retrieve_knowledge(context, source, question, limit=8, strategy='hybrid'):
    docs = documents(context, source)
    # Reuse the existing BM25 implementation, ranking each atomic document together.
    scores = bm25_scores([d['text'] for d in docs], question)
    lexical = sorted((i for i in range(len(docs)) if scores[i] > 0), key=lambda i: -scores[i])
    ranks = [lexical]
    mode = 'lexical'
    if strategy == 'hybrid':
        try:
            encoder = model()
            if encoder is not None and docs:
                import numpy as np
                key = hashlib.sha256(json.dumps(docs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                with _lock:
                    vectors = _cache.get(key)
                    if vectors is None:
                        vectors = np.array(list(encoder.embed(['passage: '+d['text'] for d in docs], batch_size=8)))
                        if len(_cache) >= 16:
                            _cache.pop(next(iter(_cache)))
                        _cache[key] = vectors
                    query = next(encoder.embed(['query: '+question]))
                ranks.append(np.argsort(-(vectors @ query)).tolist())
                mode = 'hybrid'
        except Exception:
            mode = 'lexical'
    fused = {}
    for ranking in ranks:
        for rank, index in enumerate(ranking[:20]):
            fused[index] = fused.get(index, 0) + 1/(60+rank+1)
    selected = sorted(fused, key=lambda i: (-fused[i], docs[i]['id']))[:limit]
    passages = [{**docs[i], 'score': round(fused[i], 6)} for i in selected]
    # Business constraints are compact explicit records, never the entire free-text corpus.
    # Legacy user notes/relationships remain mandatory because they may contain exclusions.
    constraints = [d for d in docs if d['section'] in ('notes', 'relationships')]
    # A legacy metric section can contain contradictory definitions. Keep all metric
    # definitions as constraints until the user migrates to a structured metric registry.
    constraints += [d for d in docs if d['section'] == 'metrics']
    # Always include authoritative structured definitions for retrieved metric records.
    constraints += [d for d in passages if d['section'] == 'metric']
    return {'mode': mode, 'model': MODEL_ID if mode == 'hybrid' else None,
            'passages': passages, 'constraints': constraints,
            'notice': 'Hybrid multilingual retrieval' if mode == 'hybrid' else 'Keyword retrieval only; local embedding model unavailable or disabled.'}


def citation_audit(answer, passages, steps=()):
    known = {d['id'] for d in passages} | {str(s['step']) for s in steps}
    refs = re.findall(r'\[([^\[\]\n]+)\]', answer)
    return {'cited': refs, 'unknown': [ref for ref in refs if ref not in known],
            'scope': 'Checks reference existence only, not semantic entailment; inspect the linked evidence.'}


def model_view(value):
    """Keep evidence IDs, omit storage routing IDs that are not valid citations."""
    if isinstance(value, dict):
        return {k: model_view(v) for k,v in value.items() if k != 'source_id'}
    if isinstance(value, list):
        return [model_view(v) for v in value]
    return value
