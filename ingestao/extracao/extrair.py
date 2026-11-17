"""Extrai as questões das provas do ENADE (PDF) para JSONL.

Cobre: segmentação por questão (RF02), objetiva/discursiva e anuladas (RF03),
metadados básicos (RF05), PDF e página de origem (RF06) e id determinístico (RF10).

PDFs de 2014, 2015 e 2017 usam uma fonte Calibri embutida sem mapa ToUnicode.
O pdfplumber devolve esses caracteres como "(cid:N)". A tabela calibri_cid.json
converte cada CID no caractere correto (ver docs/engenharia_dados.md).
"""
import argparse, collections, csv, difflib, hashlib, json, os, re, unicodedata
from pathlib import Path

import pdfplumber

RAIZ = Path(os.environ.get("ENADE_RAIZ") or Path(__file__).resolve().parents[2])
PDFS = RAIZ / "data" / "pdfs"
SAIDA = RAIZ / "data" / "questoes"
CID = {int(k): v for k, v in json.loads((Path(__file__).with_name("calibri_cid.json")).read_text(encoding="utf-8")).items()}

RE_CID = re.compile(r"\(cid:(\d+)\)")
RE_HEADER = re.compile(r"^QUEST[ÃA]O\s+(DISCURSIVA\s+)?(\d{1,2})\s*$", re.I)
RE_ALT = re.compile(r"^\(?([A-E])(?:\)|\.)?(?:\s+(.*))?$")
RE_BARCODE = re.compile(r"^\*R\d+\*$")
RE_FONTE = re.compile(r"(Acesso em|Dispon[ií]vel em|\(adaptado\)|Adaptado de)", re.I)
RUIDO = {"pv", "gb", "gab", "baixa", "alta", "prova", "pr", "prp", "ok", "discursiva", "mp"}


def sem_acento(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def slug(s):
    toks = [t for t in re.split(r"[^a-z0-9]+", sem_acento(s)) if t and t not in RUIDO]
    return "_".join(toks)


def decodificar(txt):
    """Troca (cid:N) pelo caractere. Retorna (texto, n_cid, n_desconhecidos)."""
    n = [0, 0]

    def f(m):
        n[0] += 1
        c = int(m.group(1))
        if c not in CID:
            n[1] += 1
            return ""
        return CID[c]

    return unicodedata.normalize("NFKC", RE_CID.sub(f, txt)), n[0], n[1]


def tem_midia(page):
    return bool(page.images) or len(page.curves) >= 5 or len(page.rects) >= 8 or len(page.lines) >= 8


RE_LIG = re.compile(r"(?<=[A-Za-zÀ-ÿ])(ti|tí|fi|fí|fl|ff|tt) (?=[a-zà-ÿ])")


def duas_colunas(page):
    hs = [w for w in page.extract_words() if re.match(r"qu[eE]st[ãaÃA]o", decodificar(w["text"])[0], re.I)]
    for i, a in enumerate(hs):
        for b in hs[i + 1:]:
            if abs(a["top"] - b["top"]) < 4 and abs(a["x0"] - b["x0"]) > 100:
                return True
    # página com só um cabeçalho (outro veio da página anterior): detecta a calha central
    ws = page.extract_words()
    if len(ws) < 60:
        return False
    meio = page.width / 2
    esq = sum(w["x1"] <= meio + 2 for w in ws)
    dir_ = sum(w["x0"] >= meio - 2 for w in ws)
    cruzam = len(ws) - esq - dir_
    return esq > 25 and dir_ > 25 and cruzam / len(ws) < 0.03


def ler_pagina(page):
    inteiro = page.extract_text() or ""
    if duas_colunas(page):
        meio = page.width / 2
        bruto = "\n".join((page.crop((x0, 0, x1, page.height)).extract_text() or "") for x0, x1 in ((0, meio), (meio, page.width)))
    else:
        bruto = inteiro
    txt, ncid, ndesc = decodificar(bruto)
    cab = decodificar("\n".join(inteiro.splitlines()[:4]))[0]
    return RE_LIG.sub(r"\1", txt), ncid, ndesc, cab


def titulo_curso(paginas):
    """Título do curso = rodapé repetido em todas as páginas (ex.: 'DIREITO 5')."""
    c = collections.Counter()
    for txt in paginas:
        for ln in txt.splitlines():
            ln = ln.strip()
            m = re.match(r"^(\d{1,2})\s+([A-ZÀ-Ú][A-ZÀ-Ú ,\-]{3,})$", ln) or re.match(r"^([A-ZÀ-Ú][A-ZÀ-Ú ,\-]{3,})\s+(\d{1,2})$", ln)
            if m:
                t = (m.group(2) if m.group(1).isdigit() else m.group(1)).strip()
                if not re.match(r"QUEST|RASCUNHO|FORMA|COMPONENTE|[AÁ]REA LIVRE", t, re.I):
                    c[t] += 1
    return c.most_common(1)[0][0] if c else None


def grau(*textos):
    t = sem_acento(" ".join(x for x in textos if x))
    for chave, g in (("licenciatura", "licenciatura"), ("bachar", "bacharelado"), ("tecnolog", "tecnologia"), ("_tec_", "tecnologia"), ("tec_", "tecnologia"), ("cst", "tecnologia")):
        if chave in t:
            return g
    return "bacharelado"  # padrão: sem marca de licenciatura/tecnologia no nome


def segmentar(paginas):
    """paginas: lista de (num, texto, midia, cabecalho). Retorna lista de questões brutas."""
    qs, atual, secao, fim = [], None, None, False
    for num, txt, midia, cab in paginas:
        if qs and re.search(r"QUEST\w*RIO\s+DE\s+PERCEP", cab.upper()):
            fim = True  # questionário de percepção da prova: fora do escopo
        if fim:
            continue
        for ln in txt.splitlines():
            ln = ln.strip()
            up = ln.upper()
            if up in ("FORMAÇÃO GERAL", "FORMACAO GERAL"):
                secao = "FG"; continue
            if (re.match(r"^COMPONENTE\s+ESP", up) and len(ln) <= 30 and not ln.endswith("?")) or up in ("COMPONENT", "COMPONENTE"):
                secao = "CE"; continue
            m = RE_HEADER.match(ln)
            if m:
                if atual:
                    qs.append(atual)
                atual = {"numero": int(m.group(2)), "discursiva": bool(m.group(1)), "secao": secao,
                         "pagina": num, "midia": midia, "linhas": [], "rascunho": False}
                continue
            if atual is None:
                continue
            atual["midia"] = atual["midia"] or midia
            atual["linhas"].append(ln)
    if atual:
        qs.append(atual)
    return qs


def limpar(linhas, titulo):
    out, rascunho = [], False
    for ln in linhas:
        if RE_BARCODE.match(ln):
            continue
        if titulo and re.fullmatch(rf"(\d{{1,2}}\s+)?{re.escape(titulo)}(\s+\d{{1,2}})?", ln):
            continue
        if ln.upper() in ("ÁREA LIVRE", "AREA LIVRE"):
            continue
        if ln.upper() == "RASCUNHO":
            rascunho = True
            continue
        if rascunho and re.fullmatch(r"\d{1,2}", ln):
            continue
        out.append(ln)
    return out


def juntar(linhas):
    txt = ""
    for ln in linhas:
        if not ln:
            continue
        if txt.endswith("-") and ln[:1].islower():
            txt = txt[:-1] + ln
        else:
            txt = (txt + " " + ln).strip()
    return txt


def achar_alternativas(linhas):
    """Último bloco A..E em sequência. Retorna (índice_do_A, {letra: [linhas]}) ou (None, {})."""
    pos = collections.defaultdict(list)
    for i, ln in enumerate(linhas):
        m = RE_ALT.match(ln)
        if m:
            pos[m.group(1)].append(i)
    melhor = (None, None)
    for ia in reversed(pos.get("A", [])):
        seq, atual = [ia], ia
        for letra in "BCDE":
            prox = next((i for i in pos.get(letra, []) if i > atual), None)
            if prox is None:
                break
            seq.append(prox); atual = prox
        if len(seq) >= 4 and (melhor[0] is None or len(seq) > len(melhor[1])):
            melhor = (ia, seq)
            if len(seq) == 5:
                break
    if melhor[0] is None:
        return None, {}
    ia, seq = melhor
    alts = {}
    for k, ini in enumerate(seq):
        fim = seq[k + 1] if k + 1 < len(seq) else len(linhas)
        letra = "ABCDE"[k]
        partes = []
        for j in range(ini, fim):
            m = RE_ALT.match(linhas[j]) if j == ini else None
            partes.append((m.group(2) or "") if m else linhas[j])
        alts[letra] = juntar(partes)
    return ia, alts


def separar_base(linhas):
    """Texto-base = até a última linha de fonte (Disponível em / Acesso em / adaptado)."""
    ult = None
    for i, ln in enumerate(linhas):
        if RE_FONTE.search(ln):
            ult = i
    if ult is None:
        return [], linhas
    while ult + 1 < len(linhas) and not linhas[ult].rstrip().endswith((".", ")")) and ult - 0 < len(linhas) - 1 and ult < i:
        ult += 1
    return linhas[: ult + 1], linhas[ult + 1:]


def ler_gabarito(pdf):
    mapa = {}
    try:
        with pdfplumber.open(pdf) as doc:
            txt = "\n".join(decodificar(p.extract_text() or "")[0] for p in doc.pages)
    except Exception:
        return mapa
    for ln in txt.splitlines():
        m = re.match(r"^\s*(?:QUEST[ÃA]O\s+)?(\d{1,2})\s+(ANULAD[AO]|[A-E])\s*$", ln.strip(), re.I)
        if m:
            mapa.setdefault(int(m.group(1)), m.group(2).upper())
    return mapa


def achar_gabarito(arquivo, gabaritos):
    pref = re.match(r"^(\d+)_", arquivo.name)
    if pref:
        for g in gabaritos:
            if g.name.startswith(pref.group(1) + "_"):
                return g
    chaves = {slug(g.stem): g for g in gabaritos}
    c = difflib.get_close_matches(slug(arquivo.stem), list(chaves), n=1, cutoff=0.6)
    return chaves[c[0]] if c else None


def processar(pdf, ano, gabaritos):
    with pdfplumber.open(pdf) as doc:
        paginas, ncid, ndesc = [], 0, 0
        for i, page in enumerate(doc.pages, 1):
            txt, a, b, cab = ler_pagina(page)
            ncid += a; ndesc += b
            paginas.append((i, txt, tem_midia(page), cab))
    titulo = titulo_curso([p[1] for p in paginas])
    gpdf = achar_gabarito(pdf, gabaritos)
    gab = ler_gabarito(gpdf) if gpdf else {}
    curso = slug(titulo) if titulo else ""
    if not curso or curso in ("bacharelado", "licenciatura", "tecnologia"):
        curso = re.sub(r"^\d+_", "", slug(pdf.stem))
    gr = grau(pdf.stem, titulo)
    out = []
    for q in segmentar(paginas):
        linhas = limpar(q["linhas"], titulo)
        discursiva = q["discursiva"]
        alts, base, enun = {}, [], []
        if discursiva:
            base, enun = separar_base(linhas)
        else:
            ia, alts = achar_alternativas(linhas)
            corpo = linhas[:ia] if ia is not None else linhas
            base, enun = separar_base(corpo)
        tipo_q = "discursiva" if discursiva else "objetiva"
        g = gab.get(q["numero"]) if not discursiva else None
        anulada = bool(g) and g.startswith("ANULAD")
        qid = hashlib.sha1(f"{ano}|{pdf.stem}|{tipo_q}|{q['numero']}".encode()).hexdigest()[:16]
        suspeita = (not discursiva and len(alts) < 5) or (not (juntar(enun) or juntar(base)))
        out.append({
            "id": qid, "ano": int(ano), "curso": curso, "curso_titulo": titulo, "grau": gr,
            "tipo_prova": q["secao"], "tipo_questao": tipo_q, "numero": q["numero"],
            "texto_base": juntar(base), "enunciado": juntar(enun), "alternativas": alts,
            "gabarito": None if (anulada or discursiva) else g, "anulada": anulada,
            "pdf_origem": pdf.relative_to(RAIZ).as_posix(), "pagina": q["pagina"],
            "tem_midia": q["midia"], "competencias": [], "objetos_conhecimento": [],
            "texto_degradado": bool(ncid) and ndesc / max(ncid, 1) > 0.02,
            "suspeita": suspeita,
        })
    return curso, out, gpdf is not None, ncid, ndesc


def main():
    ap = argparse.ArgumentParser(description="PDF das provas -> JSONL de questões")
    ap.add_argument("--filtro", nargs="*", default=[], help="expressões regulares sobre o nome do arquivo (ex.: direito sis_inf)")
    ap.add_argument("--anos", nargs="*", default=[])
    a = ap.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    resumo = []
    for pasta in sorted(PDFS.iterdir()):
        ano = pasta.name
        if not ano.isdigit() or (a.anos and ano not in a.anos):
            continue
        gabaritos = list((pasta / "gabarito").glob("*.pdf"))
        for pdf in sorted((pasta / "prova").glob("*.pdf")):
            if re.search(r"_pv_[2-9]\.pdf$", pdf.name.lower()):
                continue  # 2025: demais cadernos repetem as mesmas questões
            if a.filtro and not any(re.search(f, slug(pdf.stem)) for f in a.filtro):
                continue
            try:
                curso, qs, achou, ncid, ndesc = processar(pdf, ano, gabaritos)
            except Exception as e:
                print(f"! {ano}/{pdf.name}: {e}")
                continue
            with open(SAIDA / f"{ano}_{pdf.stem}.jsonl", "w", encoding="utf-8") as f:
                for q in qs:
                    f.write(json.dumps(q, ensure_ascii=False) + "\n")
            obj = [q for q in qs if q["tipo_questao"] == "objetiva"]
            resumo.append([ano, pdf.name, curso, len(qs), len(obj), len(qs) - len(obj), sum(q["suspeita"] for q in qs),
                           sum(q["anulada"] for q in qs), sum(q["gabarito"] is not None for q in obj), achou, ncid, ndesc])
            print(f"{ano} {pdf.name:42} {curso[:28]:28} q={len(qs):3} suspeitas={resumo[-1][6]:2} gab={'ok' if achou else 'NAO'} cid={ncid}/{ndesc}")
    with open(RAIZ / "data" / "extracao_resumo.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ano", "arquivo", "curso", "questoes", "objetivas", "discursivas", "suspeitas", "anuladas", "com_gabarito", "achou_gabarito", "cid_total", "cid_desconhecidos"])
        w.writerows(resumo)


if __name__ == "__main__":
    main()
