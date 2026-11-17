"""Cria os tópicos Kafka. Uso: python -m ingestao.producer.criar_topicos"""
from confluent_kafka.admin import AdminClient, NewTopic

from comum.config import PARTICOES, TOPICO, TOPICO_ERROS, kafka_conf


def main():
    admin = AdminClient(kafka_conf())
    novos = [
        NewTopic(TOPICO, num_partitions=PARTICOES, replication_factor=1),
        NewTopic(TOPICO_ERROS, num_partitions=1, replication_factor=1),
    ]
    for nome, fut in admin.create_topics(novos).items():
        try:
            fut.result()
            print(f"tópico criado: {nome}")
        except Exception as e:
            print(f"{nome}: {e}")


if __name__ == "__main__":
    main()
