# Configuration

Perry reads `config/config.json` (copy it from `config/config_example.json`). The schema is the pydantic
`Config` in [`config/config.py`](../config/config.py), loaded by `ConfigService`. LLM API keys are read
separately from a repo-root `.env`.

## `config.json` fields

| Field | Required | What it's for |
|-------|----------|---------------|
| `experiment_name` | optional | Scopes the Elasticsearch indices this run reads (`falco-<experiment_name>` / `sysflow-<experiment_name>`). |
| `elastic_config.api_key` | yes | Elasticsearch credential (the telemetry store). |
| `elastic_config.port` | yes | Elasticsearch port (e.g. `9200`). |
| `external_ip` | yes | Address telemetry exporters/queries use to reach Elasticsearch. |
| `openstack_config.ssh_key_name` | yes | OpenStack keypair name used to reach the range. |
| `openstack_config.ssh_key_path` | yes | Local path to that private key (e.g. `~/perry_key.pem`). |
| `incalmo_config.path` | optional | Path to the range/attacker (Incalmo) integration checkout — set only if used. |
| `mhbench_config.path` | optional | Path to the MHBench checkout, when the range integration needs it. |
| `caldera_config` | optional | Legacy Caldera integration (`api_key`, `port`, `external`, `python_path`, `caldera_path`). |
| `llm_api_keys` | optional | `open_ai` / `anthropic` / `google`. **See the note below — the LLM strategies actually read keys from `.env`.** |
| `experiment_timeout_minutes` | yes | Overall per-experiment time budget. |

`Config` also exposes computed `.falco_index` / `.sysflow_index` properties that resolve the per-experiment
index names from `experiment_name` (see [telemetry.md](telemetry.md)).

## `.env` (LLM keys)

Copy [`.env.example`](../.env.example) to `.env` (gitignored). The LLM agent layer loads keys from this
file with `override=True` (so an already-exported empty var from the harness doesn't win). Supported
providers: OpenAI, Anthropic, Google — plus OpenRouter and a LiteLLM gateway (see [agents.md](agents.md)).

## Required vs optional

Only the **core runtime** is required: `elastic_config`, `openstack_config`, `external_ip`, and
`experiment_timeout_minutes`. Every **plugin/integration-specific** block — `incalmo_config`,
`mhbench_config`, `caldera_config`, `llm_api_keys` — is optional; set only the ones the run actually uses.
(`config_example.json` validates as shipped.)

## One thing to reconcile (flagged for the author)

- **`llm_api_keys` vs `.env`.** The config schema has an `llm_api_keys` block, but the LLM strategies read
  keys from `.env`, not from `config.llm_api_keys`. Decide which is authoritative and document/remove the
  other.
