from pydantic import BaseModel
from typing import Optional


class ElasticSearchConfig(BaseModel):
    api_key: str
    port: int


class CalderaConfig(BaseModel):
    api_key: str
    port: int
    external: bool = True
    python_path: str = ""
    caldera_path: str = ""


class IncalmoConfig(BaseModel):
    path: str  # Path to the Incalmo project directory


class MHBenchConfig(BaseModel):
    path: str  # Path to the MHBench project directory


class OpenstackConfig(BaseModel):
    ssh_key_name: str
    ssh_key_path: str


class LLMAPIKeys(BaseModel):
    open_ai: str = ""
    anthropic: str = ""
    google: str = ""


class Config(BaseModel):
    # Name of the experiment this defender instance belongs to. Optional so
    # standalone/ad-hoc use still validates, but the runners always set it: it is
    # what scopes this run's Elasticsearch indices away from every other run
    # sharing the same ES (see defender/telemetry/index_names.py).
    experiment_name: Optional[str] = None

    # Core runtime (always needed): the telemetry store, the range credentials, and timing.
    elastic_config: ElasticSearchConfig
    openstack_config: OpenstackConfig
    external_ip: str
    experiment_timeout_minutes: int

    # Plugin / integration-specific — optional; set only the ones the run actually uses, so a run that
    # doesn't touch an integration (e.g. no LLM strategy, or a non-Caldera range) still validates.
    llm_api_keys: Optional[LLMAPIKeys] = None       # only for LLM strategies (keys also load from .env)
    incalmo_config: Optional[IncalmoConfig] = None  # the Incalmo/range integration path
    mhbench_config: Optional[MHBenchConfig] = None  # the MHBench checkout path
    caldera_config: Optional[CalderaConfig] = None  # legacy Caldera integration

    @property
    def falco_index(self) -> str:
        from defender.telemetry.index_names import falco_index

        return falco_index(self.experiment_name)

    @property
    def sysflow_index(self) -> str:
        from defender.telemetry.index_names import sysflow_index

        return sysflow_index(self.experiment_name)
