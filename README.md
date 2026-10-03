# Perry

An autonomous **cyber-defense framework** for [MHBench](https://github.com/cylabcyberautonomy/MHBench)-style cyber-range
experiments. Perry runs a defender against a live attacker on a deployed victim network: it ingests host
telemetry (Falco / SysFlow), decides what to do with a pluggable **strategy** (from static decoys to an
LLM-driven SOC), and executes **active responses** on the range — deploy decoys, plant honey
credentials, restore a compromised host, block a C2 IP.

> **Perry is the defender-side library.** It has no CLI or `main` of its own: an external experiment
> harness (the "arena", with lineage from MHBench / Incalmo) constructs a `Defender` and drives its
> lifecycle (`prepare → start → run` loop), chooses the strategy and LLM model, deploys the OpenStack
> range, and owns the Elasticsearch that telemetry ships into. See [docs/architecture.md](docs/architecture.md)
> for the run model and how to drive a `Defender`.

## What it does

- **Telemetry → events.** A pub/sub `TelemetryService` pulls Falco/SysFlow records from a per-experiment
  Elasticsearch index and turns them into high-level events (`SuspiciousHost`, `DecoyCredentialUsed`, …).
- **Strategies decide.** A `Strategy` subscribes to those events and dispatches actions — e.g. the
  `FalcoLLM` SOC triages a suspicious host with an LLM agent and restores it only on confirmed malware;
  static strategies pre-plant decoys and honey credentials.
- **Actuators act.** Response actions (`capabilities/`) are executed against the OpenStack range by
  actuators (`orchestrator/openstack_actuators/`) via the OpenStack SDK and Ansible.

## Quick start

Perry is driven by the harness, but to set it up:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

cp config/config_example.json config/config.json   # then edit it — see docs/configuration.md
```

- Put LLM API keys in a local `.env` (gitignored) — see [`.env.example`](.env.example).
- Perry acts on an MHBench-deployed OpenStack range; point the config at your cloud.
- SSH keys for range servers are generated at setup time (none are shipped in the repo).

Then the harness imports Perry, builds a `Defender`, and runs it. See
[docs/setup.md](docs/setup.md) for the full setup and [docs/architecture.md](docs/architecture.md) for
how to construct and drive one.

## Documentation

The [`docs/`](docs/) wiki:

| Page | What it covers |
|------|----------------|
| [architecture.md](docs/architecture.md) | The run model (library + harness), the `prepare/start/run` lifecycle, and the per-tick telemetry→strategy→actions pipeline. |
| [setup.md](docs/setup.md) | Install, configure, and drive a defender against a range. |
| [configuration.md](docs/configuration.md) | `config.json` + `.env` reference. |
| [strategies.md](docs/strategies.md) | The strategy catalog, the `Strategy` interface, and how to add one. |
| [telemetry.md](docs/telemetry.md) | The telemetry bus, analysis implementations, and event types. |
| [responses.md](docs/responses.md) | The action catalog (capabilities + actuators) and safety guards. |
| [agents.md](docs/agents.md) | LLM agents, model providers, and cost logging. |
| [ansible.md](docs/ansible.md) | The Ansible playbook layout and runner. |

## Layout

```
defender/        the framework: Defender.py (loop), strategy/, telemetry/, orchestrator/,
                 capabilities/, agents/, arsenal/
ansible/         playbooks: sensors (Falco/SysFlow), decoys, honey creds, range setup, vuln injection
config/          config loader + config_example.json
environment/     network/topology helpers
utility/         OpenStack + shared helpers
```

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2025 Lakshmi Adiga.
