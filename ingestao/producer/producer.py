"""Publica as questões (JSONL) no Kafka (RF07).

Uso: python -m ingestao.producer.producer [--filtro texto ...] [--limite N]
A chave da mensagem é o id da questão: o mesmo documento sempre cai na mesma partição.
Linhas inválidas vão para o tópico de erros e não interrompem a publicação (RF11).
"""
import argparse, json, time
from pathlib import Path

from confluent_kafka import Producer

from comum.config import RAIZ, TOPICO, TOPICO_ERROS, kafka_conf
from comum.documento import validar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--filtro", nargs="*", default=[], help="só arquivos cujo nome contém algum destes trechos")
    ap.add_argument("--limite", type=int, default=0, help="máximo de mensagens (0 = todas)")
    ap.add_argument("--pasta", default=str(RAIZ / "data" / "questoes"))
    a = ap.parse_args()

    falhas = []
    p = Producer(kafka_conf(**{
        "enable.idempotence": True, "acks": "all", "linger.ms": 20,
        "compression.type": "lz4", "retries": 10,
    }))

    def entregue(err, msg):
        if err is not None:
            falhas.append(str(err))

    enviados = erros = 0
    t0 = time.time()
    arquivos = sorted(Path(a.pasta).glob("*.jsonl"))
    for arq in arquivos:
        if a.filtro and not any(f in arq.name for f in a.filtro):
            continue
        with open(arq, encoding="utf-8") as fh:
            for n, linha in enumerate(fh, 1):
                if not linha.strip():
                    continue
                if a.limite and enviados + erros >= a.limite:
                    break
                doc, motivo = validar(linha)
                if motivo:
                    erros += 1
                    p.produce(TOPICO_ERROS, key=f"{arq.name}:{n}".encode(), on_delivery=entregue,
                              value=json.dumps({"origem": "producer", "arquivo": arq.name, "linha": n,
                                                "motivo": motivo, "original": linha.strip()[:2000]},
                                               ensure_ascii=False).encode("utf-8"))
                    continue
                while True:
                    try:
                        p.produce(TOPICO, key=doc["id"].encode(), value=linha.strip().encode("utf-8"),
                                  on_delivery=entregue)
                        break
                    except BufferError:  # fila local cheia: espera esvaziar
                        p.poll(0.5)
                enviados += 1
                p.poll(0)
    p.flush()
    dt = max(time.time() - t0, 1e-9)
    print(f"publicadas={enviados} invalidas={erros} falhas_de_entrega={len(falhas)} "
          f"tempo={dt:.2f}s vazao={enviados / dt:.0f} msg/s")
    if falhas:
        raise SystemExit(f"{len(falhas)} mensagens não entregues: {falhas[0]}")


if __name__ == "__main__":
    main()
