"""Confere perda e duplicação: ids no JSONL x documentos no índice (RNF04, RF10).
Uso: python -m ingestao.verificar_indexacao"""
import json
from collections import Counter

import requests

from comum.config import ES_INDICE, ES_URL, RAIZ


def main():
    esperados = Counter()
    for f in sorted((RAIZ / "data" / "questoes").glob("*.jsonl")):
        for linha in f.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                esperados[json.loads(linha)["id"]] += 1
    requests.post(f"{ES_URL}/{ES_INDICE}/_refresh", timeout=30)
    r = requests.get(f"{ES_URL}/{ES_INDICE}/_count", timeout=30).json()
    no_indice = r["count"]
    # _id é único por definição no ES; se o count bate com os ids únicos do arquivo, não há perda nem duplicata
    unicos = len(esperados)
    ids_repetidos_no_arquivo = sum(1 for v in esperados.values() if v > 1)
    print(f"ids únicos no JSONL: {unicos} (repetidos no próprio arquivo: {ids_repetidos_no_arquivo})")
    print(f"documentos no índice: {no_indice}")
    print("OK: sem perda e sem duplicata" if no_indice == unicos else f"DIFERENÇA: {no_indice - unicos:+d}")


if __name__ == "__main__":
    main()
