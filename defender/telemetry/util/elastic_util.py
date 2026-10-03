from elasticsearch import Elasticsearch
from config.config import Config


def get_elasticsearch_conn(config: Config):
    elasticsearch_server = f"https://localhost:{config.elastic_config.port}"
    elasticsearch_api_key = config.elastic_config.api_key

    elasticsearch_conn = Elasticsearch(
        elasticsearch_server,
        basic_auth=("elastic", elasticsearch_api_key),
        verify_certs=False,
    )
    if not elasticsearch_conn.ping():
        raise Exception("Connection to elasticsearch failed")

    return elasticsearch_conn
