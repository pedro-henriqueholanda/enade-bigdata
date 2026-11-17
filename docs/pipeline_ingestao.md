# Pipeline de ingestão: Kafka para Elasticsearch

```
data/questoes/*.jsonl -> producer -> [questoes] -> consumer -> Elasticsearch (índice questoes)
                                   \-> [questoes.erros] (DLQ)  <- producer e consumer
```

## Topologia (decisões a justificar no relatório)

| Item | Valor | Motivo |
|---|---|---|
| Brokers Kafka | 1 (KRaft, papéis broker+controller) | laboratório com 1 máquina; replicação 1 |
| Partições de `questoes` | 3 | permite até 3 consumidores do mesmo grupo em paralelo; chave = id da questão |
| Partições de `questoes.erros` | 1 | volume baixo; ordem de chegada preservada |
| Shards do índice | 3 | uma partição por shard facilita escalar para 3 nós; o acervo é pequeno, então o ganho aqui é de projeto, não de desempenho |
| Réplicas do índice | 0 | só há 1 nó; com 1 nó, réplica 1 deixaria o cluster em `yellow` |

Em produção: 3 brokers com replicação 3 e `min.insync.replicas=2`; índice com réplica 1.

## Garantias

- **Sem perda (RF09):** commit manual do offset só depois de indexar o lote. Queda antes do commit significa que o lote é relido.
- **Sem duplicata (RF10):** `_id` do documento = `id` determinístico (SHA-1 de ano, arquivo, tipo e número). Reler ou reprocessar o arquivo sobrescreve o mesmo documento.
- **Mensagem ruim não para o fluxo (RF11):** JSON inválido, campo obrigatório faltando ou rejeição do mapping (`dynamic: strict`) vão para `questoes.erros` com o motivo, a partição e o offset de origem.
- **Elasticsearch fora do ar:** o consumidor repete o lote com espera crescente (1 s até 30 s) e não confirma o offset.
- **Produtor:** `enable.idempotence=true` e `acks=all`.

## Índice

`infra/elasticsearch/mapping.json`. Campos de filtro como `keyword` (curso, ano, tipo_questao, competencias).
Campos de busca como `text`:

- Indexação: `lowercase`, remoção de stopwords do português, `asciifolding`, stemmer `brazilian`.
- Busca: igual, mais `synonym_graph` (ética, moral, deontologia; corrupção, improbidade etc.), só no lado da
  consulta, para poder mudar os sinônimos sem reindexar.

## Experimento de falha (RNF04)

1. Subir tudo, criar índice e tópicos, publicar.
2. Consumir devagar: `python -m consumer.consumer --lote 20 --atraso-ms 300`.
3. Matar o processo à força no meio da carga (`Stop-Process -Name python -Force`). Anotar o lag.
4. Subir de novo o consumidor com `--sair-ocioso 20`. Ele retoma do último offset confirmado.
5. `python -m ingestao.verificar_indexacao` deve mostrar o mesmo número de ids únicos e de documentos.
6. Publicar tudo outra vez e consumir: a contagem não muda (idempotência).
7. Variante: `docker compose stop elasticsearch` durante o consumo, esperar as tentativas, `docker compose start elasticsearch`.
