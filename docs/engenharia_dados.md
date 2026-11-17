# Engenharia de dados: extração das provas

Script: `ingestao/extracao/extrair.py` (pdfplumber). Saída: um `.jsonl` por prova em `data/questoes/`
(não versionado) e o resumo `data/extracao_resumo.csv`.

## Estratégia

1. **Segmentação por questão (RF02):** cada cabeçalho `QUESTÃO NN` / `QUESTÃO DISCURSIVA NN` abre um documento.
2. **Tipo e seção (RF03, RF05):** objetiva ou discursiva pelo cabeçalho; FG ou CE pelos títulos
   "FORMAÇÃO GERAL" e "COMPONENTE ESPECÍFICO".
3. **Alternativas:** último bloco A–E em sequência; texto-base separado pela última linha de fonte
   (`Disponível em`, `Acesso em`, `adaptado`).
4. **Gabarito e anuladas (RF03):** o PDF do gabarito é pareado à prova (prefixo numérico ou nome).
   Questão anulada fica no índice com `anulada = true`.
5. **Rastreabilidade (RF06):** `pdf_origem` e `pagina` em todo documento.
6. **Idempotência (RF10):** `id` = SHA-1 de `ano|arquivo|tipo|número` (16 hex). Reprocessar gera o mesmo id.

## Problemas encontrados e tratamento

| Problema | Onde | Tratamento |
|---|---|---|
| Fonte Calibri embutida sem mapa ToUnicode: o texto sai como `(cid:N)` | 2014, 2015, 2017 | tabela `calibri_cid.json` (CID para caractere) |
| Duas colunas: o cabeçalho de uma questão cai no meio da linha de outra | 2014, 2015, 2017 | detecção de colunas por cabeçalhos lado a lado ou pela calha central da página; leitura por coluna |
| Palavra `QUESTÃO` e número no mesmo token CID | 2017 | decodificar antes de comparar |
| Título "COMPONENTE ESPECÍFICO" cortado entre colunas | 2012 | reconhece os dois fragmentos |
| Nome do curso vindo do rodapé errado (ex.: `bacharelado`) | 2014 | usa o nome do arquivo, sem o prefixo numérico |

Resultado nas 11 provas de computação e Direito processadas até agora (2012, 2014, 2015, 2017, 2018, 2019):
440 questões, todas as provas com 40 questões (35 objetivas + 5 discursivas; 10 de FG e 30 de CE),
378 objetivas com gabarito, 7 anuladas, 1 questão suspeita (menos de 5 alternativas reconhecidas).

## Limitações conhecidas

- `tem_midia` é verdadeiro em todas as questões: o critério (imagens, curvas, retângulos, linhas)
  dispara em bordas e filetes de toda página. Precisa de critério por região da questão antes de
  usar para decidir o que vai para conversão (RF04).
- `texto_degradado` marca as provas de Engenharia de Computação (2014 e 2019): parte dos glifos
  não está na tabela CID.
- `competencias` e `objetos_conhecimento` ainda vazios (a prova não traz essa informação).
- Provas de 2021 em diante não foram extraídas: o download dessas edições falhou (ver `data/manifest.csv`).

## Qualidade medida (RNF03)

Planilha `data/amostra_validacao.csv`: 50 questões sorteadas (semente 42), a preencher manualmente
com 1/0 em segmentação, alternativas e gabarito. A taxa de acerto vem dessa planilha.
