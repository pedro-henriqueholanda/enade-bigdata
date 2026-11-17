import json, unittest
from comum.documento import para_indice, validar

BASE = {"id": "abc", "ano": 2018, "curso": "direito", "tipo_questao": "objetiva", "numero": 3,
        "pdf_origem": "data/pdfs/2018/prova/direito.pdf", "pagina": 5,
        "alternativas": {"A": "x"}, "suspeita": False, "texto_degradado": False}


class TesteDocumento(unittest.TestCase):
    def test_valido(self):
        d, motivo = validar(json.dumps(BASE))
        self.assertIsNone(motivo)
        self.assertEqual(d["id"], "abc")

    def test_json_quebrado(self):
        _, motivo = validar(b'{"id": "x"')
        self.assertTrue(motivo.startswith("json_invalido"))

    def test_bytes_invalidos(self):
        _, motivo = validar(b"\xff\xfe")
        self.assertTrue(motivo.startswith("json_invalido"))

    def test_falta_campo_e_tipo(self):
        ruim = {k: v for k, v in BASE.items() if k != "pagina"}
        ruim["ano"] = "2018"
        _, motivo = validar(json.dumps(ruim))
        self.assertIn("falta_pagina", motivo)
        self.assertIn("tipo_ano", motivo)

    def test_tipo_questao_invalido(self):
        _, motivo = validar(json.dumps({**BASE, "tipo_questao": "outra"}))
        self.assertEqual(motivo, "tipo_questao_invalido")

    def test_para_indice_mantem_id_e_remove_flags(self):
        i, doc = para_indice(BASE)
        self.assertEqual(i, "abc")
        self.assertNotIn("suspeita", doc)
        self.assertEqual(doc["competencias"], [])

    def test_todos_os_jsonl_reais_passam(self):
        from comum.config import RAIZ
        total = 0
        for f in (RAIZ / "data" / "questoes").glob("*.jsonl"):
            for linha in f.read_text(encoding="utf-8").splitlines():
                if linha.strip():
                    _, motivo = validar(linha)
                    self.assertIsNone(motivo, f"{f.name}: {motivo}")
                    total += 1
        self.assertGreater(total, 0)


if __name__ == "__main__":
    unittest.main()
