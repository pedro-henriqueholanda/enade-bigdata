"""Coleta provas, gabaritos e padrões de resposta do ENADE (RF01)."""
import csv, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

BASE = "https://www.gov.br/inep/pt-br/areas-de-atuacao/avaliacao-e-exames-educacionais/enade/provas-e-gabaritos"
RAIZ = Path(__file__).resolve().parents[2]
DEST = RAIZ / "data" / "pdfs"
MANIFEST = RAIZ / "data" / "manifest.csv"
EXTRA = Path(__file__).with_name("urls_extra.txt")
HEADERS = {"User-Agent": "Mozilla/5.0 (projeto academico UniCatolica Big Data)"}
sess = requests.Session()
sess.headers.update(HEADERS)


def get(url, **kw):
    for tentativa in range(3):
        try:
            r = sess.get(url, timeout=60, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            print(f"  ! {url} ({e}), tentativa {tentativa+1}")
            time.sleep(2 * (tentativa + 1))
    return None


def links_da_pagina(url):
    r = get(url)
    if not r:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    return [urljoin(url, a["href"]) for a in soup.find_all("a", href=True)]


def descobrir_pdfs():
    pdfs, subpaginas = set(), set()
    for link in links_da_pagina(BASE):
        l = link.split("#")[0]
        if l.lower().endswith(".pdf") or "download.inep.gov.br" in l:
            pdfs.add(l)
        elif l.startswith(BASE) and l.rstrip("/") != BASE:
            subpaginas.add(l)
    print(f"{len(subpaginas)} subpaginas encontradas")
    for sp in sorted(subpaginas):
        time.sleep(1)
        for link in links_da_pagina(sp):
            l = link.split("#")[0]
            if l.lower().endswith(".pdf") or "download.inep.gov.br" in l:
                pdfs.add(l)
    if EXTRA.exists():
        pdfs |= set(re.findall(r"https?://\S+?\.pdf", EXTRA.read_text(encoding="utf-8"), flags=re.I))
    return sorted(pdfs)


def classificar(url):
    p = unquote(urlparse(url).path)
    nome = Path(p).name.lower()
    partes = p.lower().split("/")
    m = re.search(r"(?<!\d)(20[0-2]\d)(?!\d)", p)
    ano = m.group(1) if m else "sem_ano"
    if "padrao_resposta" in partes or "discursiva" in nome:
        tipo = "padrao_resposta"
    elif "gabaritos" in partes or re.search(r"(^|_)gb(_|\.)", nome):
        tipo = "gabarito"
    elif re.search(r"(^|_)mp(_|\.)", nome):
        tipo = "mapa_prova"
    elif re.search(r"ledor|ampliada", nome):
        tipo = "prova_acessivel"
    else:
        tipo = "prova"
    return ano, tipo, nome


def baixar(url, ano, tipo, nome):
    destino = DEST / ano / tipo / nome
    if destino.exists() and destino.stat().st_size > 0:
        return "ja_existia", destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    r = get(url)
    if not r or not r.content.startswith(b"%PDF"):
        return "falhou", destino
    destino.write_bytes(r.content)
    return "baixado", destino


def main():
    pdfs = descobrir_pdfs()
    print(f"{len(pdfs)} PDFs candidatos")
    if not pdfs:
        print("Nada encontrado. Coloque URLs em ingestao/coleta/urls_extra.txt")
        sys.exit(1)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ano", "tipo", "arquivo", "url", "status", "bytes"])
        for i, url in enumerate(pdfs, 1):
            ano, tipo, nome = classificar(url)
            status, destino = baixar(url, ano, tipo, nome)
            tam = destino.stat().st_size if destino.exists() else 0
            w.writerow([ano, tipo, nome, url, status, tam])
            print(f"[{i}/{len(pdfs)}] {status:10} {ano}/{tipo}/{nome}")
            time.sleep(0.5)


if __name__ == "__main__":
    main()