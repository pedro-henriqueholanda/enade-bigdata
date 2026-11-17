"""Configuração compartilhada (lida do ambiente; nada de segredo no código)."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:29092")
TOPICO = os.environ.get("TOPICO_QUESTOES", "questoes")
TOPICO_ERROS = os.environ.get("TOPICO_ERROS", "questoes.erros")
GRUPO = os.environ.get("KAFKA_GRUPO", "indexador-es")
PARTICOES = int(os.environ.get("KAFKA_PARTICOES", "3"))

ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
ES_INDICE = os.environ.get("ES_INDICE", "questoes")


def kafka_conf(**extra):
    """Configuração base do cliente Kafka. A segurança (SASL/GSSAPI) entra por variáveis
    KAFKA_SECURITY_PROTOCOL, KAFKA_SASL_MECHANISM etc. na etapa de Kerberos."""
    conf = {"bootstrap.servers": KAFKA_BOOTSTRAP}
    proto = os.environ.get("KAFKA_SECURITY_PROTOCOL")
    if proto:
        conf["security.protocol"] = proto
    if os.environ.get("KAFKA_SASL_MECHANISM"):
        conf["sasl.mechanism"] = os.environ["KAFKA_SASL_MECHANISM"]
    if os.environ.get("KAFKA_SASL_KERBEROS_SERVICE_NAME"):
        conf["sasl.kerberos.service.name"] = os.environ["KAFKA_SASL_KERBEROS_SERVICE_NAME"]
    conf.update(extra)
    return conf
