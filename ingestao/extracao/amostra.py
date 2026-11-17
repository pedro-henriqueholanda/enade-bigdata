"""Gera a planilha de validação manual (RNF03): 50 questões sorteadas, com semente fixa."""
import csv, json, random
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
qs = [json.loads(l) for f in sorted((RAIZ / "data" / "questoes").glob("*.jsonl"))
      for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
random.seed(42)
amostra = random.sample(qs, min(50, len(qs)))
saida = RAIZ / "data" / "amostra_validacao.csv"
if saida.exists():
    raise SystemExit(f"{saida.name} já existe (pode conter sua validação manual). Apague-o antes de gerar de novo.")
with open(saida, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(["id", "pdf_origem", "pagina", "numero", "tipo_questao", "segmentacao_ok", "alternativas_ok", "gabarito_ok", "obs"])
    for q in amostra:
        w.writerow([q["id"], q["pdf_origem"], q["pagina"], q["numero"], q["tipo_questao"], "", "", "", ""])
print(f"{len(amostra)} questões -> {saida}")
