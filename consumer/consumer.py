"""Consome o tópico `questoes` e indexa no Elasticsearch (RF08, RF09, RF10, RF11).

Garantias:
* o offset só é confirmado (commit manual) DEPOIS que o lote foi indexado e os erros foram
  para a DLQ; se o consumidor cair antes, o lote é relido (entrega pelo menos uma vez);
* o `_id` do documento é o id determinístico, então a releitura não gera duplicata;
* mensagem inválida ou rejeitada pelo mapping vai para `questoes.erros` e o fluxo segue;
* Elasticsearch fora do ar: o lote é repetido com espera crescente, sem commit.

Uso: python -m consumer.consumer [--lote 200] [--sair-ocioso 20] [--atraso-ms 0]
"""
import argparse, json, signal, time

from confluent_kafka import Consumer, KafkaError, Producer
from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import ApiError, ConnectionError as ESConnectionError, TransportError

from comum.config import ES_INDICE, ES_URL, GRUPO, RAIZ, TOPICO, TOPICO_ERROS, kafka_conf
from comum.documento import para_indice, validar

parar = False


def _sinal(*_):
    global parar
    parar = True


def lag_total(c):
    total = 0
    for tp in c.assignment():
        _, alto = c.get_watermark_offsets(tp, cached=False, timeout=5)
        pos = c.position([tp])[0].offset
        total += max(alto - (pos if pos >= 0 else 0), 0)
    return total


def enviar_dlq(prod, msg, motivo):
    prod.produce(TOPICO_ERROS, key=msg.key(), value=json.dumps({
        "origem": "consumer", "motivo": motivo, "topico": msg.topic(),
        "particao": msg.partition(), "offset": msg.offset(),
        "original": (msg.value() or b"").decode("utf-8", "replace")[:4000],
    }, ensure_ascii=False).encode("utf-8"))


def indexar_lote(es, prod, lote):
    """lote: lista de (msg, id, doc). Retorna (indexados, enviados_a_dlq). Lança exceção se o ES falhar."""
    acoes = [{"_op_type": "index", "_index": ES_INDICE, "_id": i, "_source": doc} for _, i, doc in lote]
    ok, itens = helpers.bulk(es, acoes, raise_on_error=False, raise_on_exception=True, stats_only=False)
    por_id = {i: m for m, i, _ in lote}
    dlq = 0
    for it in itens:
        r = it.get("index", it)
        status = r.get("status", 0)
        if status == 429 or status >= 500:
            raise TransportError(f"ES respondeu {status}: tenta o lote de novo")
        enviar_dlq(prod, por_id[r["_id"]], f"es_rejeitou_{status}: {json.dumps(r.get('error'), ensure_ascii=False)[:500]}")
        dlq += 1
    return ok, dlq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lote", type=int, default=200)
    ap.add_argument("--sair-ocioso", type=int, default=0, help="encerra após N s sem mensagens (0 = roda sempre)")
    ap.add_argument("--atraso-ms", type=int, default=0, help="espera por lote (serve para o experimento de falha)")
    a = ap.parse_args()
    signal.signal(signal.SIGINT, _sinal)
    signal.signal(signal.SIGTERM, _sinal)

    c = Consumer(kafka_conf(**{
        "group.id": GRUPO, "enable.auto.commit": False, "auto.offset.reset": "earliest",
        "max.poll.interval.ms": 300000,
    }))
    prod = Producer(kafka_conf(**{"enable.idempotence": True, "acks": "all"}))
    es = Elasticsearch(ES_URL, request_timeout=30)
    c.subscribe([TOPICO])

    indexados = erros = 0
    t0 = ultimo_log = ultima_msg = time.time()
    primeira = None
    print(f"consumindo '{TOPICO}' (grupo {GRUPO}) -> índice '{ES_INDICE}'")
    while not parar:
        msgs = c.consume(num_messages=a.lote, timeout=1.0)
        if not msgs:
            if a.sair_ocioso and time.time() - ultima_msg > a.sair_ocioso:
                break
            continue
        ultima_msg = time.time()
        primeira = primeira or ultima_msg
        lote = []
        for m in msgs:
            if m.error():
                if m.error().code() != KafkaError._PARTITION_EOF:
                    print("erro do Kafka:", m.error())
                continue
            doc, motivo = validar(m.value())
            if motivo:
                enviar_dlq(prod, m, motivo); erros += 1
                continue
            i, fonte = para_indice(doc)
            lote.append((m, i, fonte))
        espera = 1
        while lote and not parar:
            try:
                ok, dlq = indexar_lote(es, prod, lote)
                indexados += ok; erros += dlq
                break
            except (ESConnectionError, TransportError, ApiError) as e:
                print(f"Elasticsearch indisponível ({type(e).__name__}); nova tentativa em {espera}s")
                time.sleep(espera); espera = min(espera * 2, 30)
        if parar:
            break  # não confirma: o lote será relido
        prod.flush()
        c.commit(asynchronous=False)
        if a.atraso_ms:
            time.sleep(a.atraso_ms / 1000)
        if time.time() - ultimo_log >= 5:
            dt = time.time() - primeira
            print(f"indexados={indexados} dlq={erros} docs/s={indexados / max(dt, 1e-9):.0f} lag={lag_total(c)}")
            ultimo_log = time.time()

    dt = (ultima_msg - primeira) if primeira else 0.0
    resumo = {"indexados": indexados, "dlq": erros, "segundos": round(dt, 2),
              "docs_por_s": round(indexados / dt, 1) if dt else 0}
    print("resumo:", resumo)
    (RAIZ / "data").mkdir(exist_ok=True)
    (RAIZ / "data" / "metricas_ingestao.json").write_text(json.dumps(resumo, indent=2), encoding="utf-8")
    c.close()


if __name__ == "__main__":
    main()
