"""Cria o índice `questoes` com o mapping versionado. Uso: python -m infra.elasticsearch.criar_indice [--recriar]"""
import argparse, json, sys
from pathlib import Path

import requests

from comum.config import ES_INDICE, ES_URL

MAPPING = Path(__file__).with_name("mapping.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recriar", action="store_true", help="apaga e recria o índice (perde os dados)")
    a = ap.parse_args()
    url = f"{ES_URL}/{ES_INDICE}"
    existe = requests.head(url, timeout=30).status_code == 200
    if existe and a.recriar:
        requests.delete(url, timeout=60).raise_for_status()
        existe = False
    if existe:
        print(f"índice '{ES_INDICE}' já existe (use --recriar para refazer)")
        return
    r = requests.put(url, json=json.loads(MAPPING.read_text(encoding="utf-8")), timeout=60)
    if r.status_code >= 300:
        print(r.text); sys.exit(1)
    print(f"índice '{ES_INDICE}' criado")


if __name__ == "__main__":
    main()
