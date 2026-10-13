"""Run from the project root: python -m scripts.setup_warehouse --archive FILE --embeddings."""
import argparse
from pathlib import Path
import urllib.request

from backend.store import Store
from backend.warehouse import import_package


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--download', action='store_true', help='Download the public official Olist ZIP (CC BY-NC-SA 4.0).')
    parser.add_argument('--embeddings', action='store_true', help='Download the pretrained multilingual model; no training.')
    parser.add_argument('--storage', type=Path, default=Path('storage'))
    args = parser.parse_args()
    if args.download:
        args.storage.mkdir(parents=True, exist_ok=True)
        args.archive = args.storage / 'olist.zip'
        partial = args.storage / 'olist.zip.partial'
        with urllib.request.urlopen('https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce', timeout=120) as response, partial.open('wb') as output:
            total = 0
            while chunk := response.read(1024*1024):
                total += len(chunk)
                if total > 256*1024*1024:
                    raise ValueError('Download exceeds 256 MB.')
                output.write(chunk)
        partial.replace(args.archive)
    if args.archive:
        store = Store(args.storage)
        existing = next((s for s in store.sources() if s.get('dataset') == 'olist' and not s.get('experiment')), None)
        source = existing or import_package(store, args.archive)
        print('Warehouse:', source['id'], [(t['name'], t['rows']) for t in source['tables']], flush=True)
    if args.embeddings:
        import json
        import os
        os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
        from huggingface_hub import model_info
        from backend.retrieval import MODEL_ID, MODEL_PATH
        if (MODEL_PATH / 'onnx/model.onnx').is_file() and (MODEL_PATH / 'provenance.json').is_file():
            print('Local multilingual embedding model already installed:', MODEL_ID)
            return
        # Download into a staging directory; request-time code must never see a partial model.
        stage = MODEL_PATH.with_name(MODEL_PATH.name + '-download')
        revision = model_info(MODEL_ID).sha
        for filename in ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'onnx/model.onnx']:
            destination = stage / filename
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            partial = destination.with_suffix(destination.suffix + '.partial')
            url = f'https://huggingface.co/{MODEL_ID}/resolve/{revision}/{filename}?download=true'
            with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as output:
                total = 0
                while chunk := response.read(1024*1024):
                    total += len(chunk)
                    output.write(chunk)
                    if total % (50*1024*1024) == 0:
                        print(filename, total//(1024*1024), 'MB', flush=True)
            partial.replace(destination)
        (stage / 'provenance.json').write_text(json.dumps({'model': MODEL_ID, 'revision': revision}), encoding='utf-8')
        if not MODEL_PATH.exists():
            stage.rename(MODEL_PATH)
        print('Local multilingual embedding model ready:', MODEL_ID)


if __name__ == '__main__':
    main()
