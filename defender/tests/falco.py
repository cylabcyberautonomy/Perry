from defender.telemetry.falco.falco_basic import FalcoBasicAnalysis
from defender.telemetry.types.falco_alert import FalcoAlert
from elasticsearch import Elasticsearch
from config.config_service import ConfigService

config_service = ConfigService()


def main():
    elasticsearch_server = (
        f"https://localhost:{config_service.get_config().elastic_config.port}"
    )
    elasticsearch_api_key = config_service.get_config().elastic_config.api_key

    elasticsearch_conn = Elasticsearch(
        elasticsearch_server,
        basic_auth=("elastic", elasticsearch_api_key),
        verify_certs=False,
    )

    # Get last 10m of falco data
    query = {
        "query": {
            "range": {"@timestamp": {"gte": "now-10m"}},
        }
    }

    response = elasticsearch_conn.search(index="falco", body=query)

    for hit in response["hits"]["hits"]:
        alert = FalcoAlert(**hit["_source"])
        print(alert)


if __name__ == "__main__":
    main()
