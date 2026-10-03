from elasticsearch import Elasticsearch, BadRequestError
import os
from string import Template
from defender.agents.llm_agent import LLMAgent
from defender.agents.sysflow.sysflow_agent_report import SysFlowAgentReport
import time
from pydantic import ValidationError
from defender.telemetry.index_names import SYSFLOW_BASE

QUERY_BUDGET = 5
MAX_RESULT_STRING_LENGTH = 10000


class SysFlowAgent:
    def __init__(
        self,
        es: Elasticsearch,
        suspicious_ip: str,
        llm_model: str,
        identify_c2: bool = True,
        sysflow_index: str = SYSFLOW_BASE,
    ):
        self.es = es
        self.suspicious_ip = suspicious_ip
        # The index this run writes to. The unscoped "sysflow" mixes experiments.
        self.sysflow_index = sysflow_index
        # identify_c2 selects the preprompt: FalcoLLMC2Block needs the C2 IP, FalcoLLM does not.
        self.identify_c2 = identify_c2
        self.preprompt = self.get_preprompt()
        self.llm_agent = LLMAgent(self.preprompt, model_name=llm_model)

    def get_preprompt(self):
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        preprompt_file_name = (
            "preprompt.txt" if self.identify_c2 else "preprompt_restore.txt"
        )
        preprompt: str = ""
        with open(os.path.join(cur_dir, preprompt_file_name), "r") as preprompt_file:
            preprompt = preprompt_file.read()

        index_name = self.sysflow_index
        mapping = self.es.indices.get_mapping(index=index_name)
        props = _flatten_mapping(mapping[index_name]["mappings"]["properties"])

        parameters = {
            "ip_address": self.suspicious_ip,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "query_budget": QUERY_BUDGET,
            "index_mappings": str(props),
        }
        preprompt = Template(preprompt).substitute(parameters)
        return preprompt

    def run(self) -> SysFlowAgentReport | None:
        response = self.llm_agent.send_message("Please send your first query")

        elastic_query = self.llm_agent.extract_tag(response, "elastic_query")

        for _ in range(QUERY_BUDGET):
            query_error = False
            try:
                result = self.es.search(index=self.sysflow_index, body=elastic_query)
            except BadRequestError as e:
                result_str = f"Error: {e}"
                query_error = True

            if not query_error:
                result_str = str(result)
                if len(result_str) > MAX_RESULT_STRING_LENGTH:
                    result_str = result_str[:MAX_RESULT_STRING_LENGTH]
                    result_str += "QUERY LIMIT REACHED..."

            response = self.llm_agent.send_message(
                f"Please send your next query. The last result was: {result_str}"
            )
            elastic_query = self.llm_agent.extract_tag(response, "elastic_query")

            if self.llm_agent.is_finished():
                break

        last_message = self.llm_agent.get_last_message()
        report_str = self.llm_agent.extract_tag(last_message, "report")
        if report_str is None:
            return None

        try:
            report = SysFlowAgentReport.model_validate_json(report_str)
            return report
        except ValidationError as e:
            print(f"Error parsing report: {e}")
            return None


def _flatten_mapping(mapping, prefix=""):
    """Flatten a mapping to dotted field names mapped to es_type."""
    out = {}
    for name, meta in mapping.items():
        path = f"{prefix}{name}"
        if "properties" in meta:
            out.update(_flatten_mapping(meta["properties"], f"{path}."))
        else:
            out[path] = meta.get("type", "object")
    return out
