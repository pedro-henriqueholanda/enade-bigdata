"""Validação e preparo dos documentos de questão (sem dependências externas)."""
import json

OBRIGATORIOS = {
    "id": str, "ano": int, "curso": str, "tipo_questao": str,
    "numero": int, "pdf_origem": str, "pagina": int,
}
TIPOS_QUESTAO = {"objetiva", "discursiva"}
LISTAS = ("competencias", "objetos_conhecimento")


def decodificar(bruto):
    """bytes/str -> (dict, None) ou (None, motivo)."""
    try:
        txt = bruto.decode("utf-8") if isinstance(bruto, (bytes, bytearray)) else bruto
        d = json.loads(txt)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, f"json_invalido: {e}"
    if not isinstance(d, dict):
        return None, "json_nao_e_objeto"
    return d, None


def erros_de_schema(d):
    erros = []
    for campo, tipo in OBRIGATORIOS.items():
        v = d.get(campo)
        if v is None:
            erros.append(f"falta_{campo}")
        elif not isinstance(v, tipo) or isinstance(v, bool):
            erros.append(f"tipo_{campo}")
    if not erros:
        if not d["id"].strip():
            erros.append("id_vazio")
        if d["tipo_questao"] not in TIPOS_QUESTAO:
            erros.append("tipo_questao_invalido")
        if d["numero"] < 1 or d["pagina"] < 1:
            erros.append("numero_ou_pagina_invalido")
    alts = d.get("alternativas")
    if alts is not None and not isinstance(alts, dict):
        erros.append("tipo_alternativas")
    for campo in LISTAS:
        if d.get(campo) is not None and not isinstance(d[campo], list):
            erros.append(f"tipo_{campo}")
    return erros


def validar(bruto):
    """Retorna (documento, None) ou (None, motivo)."""
    d, motivo = decodificar(bruto)
    if motivo:
        return None, motivo
    erros = erros_de_schema(d)
    if erros:
        return None, ",".join(erros)
    return d, None


def para_indice(d):
    """Documento pronto para o Elasticsearch. O _id é o id determinístico (idempotência, RF10)."""
    doc = {k: v for k, v in d.items() if k not in ("suspeita", "texto_degradado")}
    doc["alternativas"] = d.get("alternativas") or {}
    doc["competencias"] = d.get("competencias") or []
    doc["objetos_conhecimento"] = d.get("objetos_conhecimento") or []
    return d["id"], doc
