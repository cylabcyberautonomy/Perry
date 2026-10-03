# Working in Perry

Perry is the **defender-side library** of an MHBench cyber-range experiment. This file is the practical
"how to work here" guide; the conceptual docs live in [`docs/`](docs/).

## The one thing to know first

**This repo is a library, not an application.** There is no CLI, no `main`, no run loop in it. An external
**harness** (the "arena", lineage from MHBench / Incalmo) imports Perry, constructs a `Defender` with its
five collaborators, and drives the lifecycle. You will not find `Defender(...)` being constructed anywhere
in this repo — that wiring, strategy/model selection, and the `while running: defender.run()` loop all
live in the harness. When something "starts the defender," it means the harness.

## Run model

`Defender(arsenal, strategy, telemetry_service, orchestrator, network)` (`defender/Defender.py`), driven as:

1. `prepare()` — **external arming**, run before the scenario in a throwaway setup process. Runs
   `strategy.initialize()` **iff** `strategy.ARMS_IN_SETUP` is True (slow decoy/credential deploy finishes
   and fails loudly before the attacker starts). No-op otherwise.
2. `start(prepared=True)` — in-process wiring in the loop process. Arms here for non-`ARMS_IN_SETUP`
   strategies (and legacy single-call paths); then `begin_monitoring()` stamps scenario start.
3. `run()` — one loop tick: `telemetry_service.process_telemetry()` then `strategy.run()`.

Per-tick pipeline: **telemetry pulled from Elasticsearch → parsed into high-level events → emitted to the
strategy's subscribed handlers → strategy dispatches Actions to the orchestrator.** Most strategies do
their real work in event *handlers*, so `run()` is often a `pass`.

## Architecture (where things live)

```
defender/
  Defender.py          the lifecycle object (prepare/start/run)
  strategy/            the decision policies (Strategy base + the catalog); strategy/llm/ = LLM SOCs
  telemetry/           pub/sub bus (TelemetryService) + TelemetryAnalysis impls + events/
  orchestrator/        OpenstackOrchestrator + openstack_actuators/ (the action executors)
  capabilities/        Action dataclasses (the "what" of a response; actuators are the "how")
  agents/              LLM wiring: langchain_registry, LLMAgent, sysflow/ investigation agent, token logging
  arsenal/             the per-run action budget/inventory
ansible/               playbooks + AnsibleRunner (sensors, decoys, honey creds, range/vuln setup)
config/                Config (pydantic) + ConfigService (loads config.json) + config_example.json
environment/           Network/topology helpers
utility/               OpenStack + shared helpers
```

## Extending

**Add a strategy** (`defender/strategy/`): subclass `Strategy` (`strategy/Strategy.py`), implement
`initialize(self)` (arm: deploy decoys / plant creds, and/or `telemetry_service.subscribe(EventType, handler)`),
and optionally `run(self)` (per-tick; default no-op). Set `ARMS_IN_SETUP = True` **only** if `initialize()`
is pure external arming with no subscriptions and no in-process state the loop reads (static decoy/credential
planters). There is no name→class registry here — the harness maps a selected name to your class.

**Add a telemetry analysis** (`defender/telemetry/`): subclass `TelemetryAnalysis`, implement
`process_low_level_events()` to turn raw Falco/SysFlow docs into high-level `Event`s and `emit()` them.
Strategies and analyses are paired by the harness: LLM/prompt-injection strategies need a Falco analysis
(`SuspiciousHost`/`FalcoEvent`); Reactive* strategies need a decoy-event analysis (`DecoyCredentialUsed`/
`DecoyHostInteraction`); `NoTelemetry` is for non-instrumented ranges.

**Add a response action**: define a parameter-holder `Action` dataclass in `capabilities/`, then an executor
in `orchestrator/openstack_actuators/` and register it in `OpenstackOrchestrator`'s actuator table (keyed by
the capability class name). Actuators run via the OpenStack SDK + `AnsibleRunner`.

## Conventions

- **Actions are data.** Strategies build capability dataclasses and hand them to the orchestrator; they
  don't touch OpenStack/Ansible directly.
- **Per-experiment ES indices.** Telemetry is scoped to `falco-<exp>` / `sysflow-<exp>` (`telemetry/index_names.py`)
  because the shared Elasticsearch is persistent and Falco/SysFlow docs carry no experiment discriminator —
  there's a documented cross-experiment contamination incident behind this. Keep it.
- **Logging/config:** `structlog` throughout; config is pydantic (`config/config.py`) loaded by `ConfigService`.
- **LLM keys** load from a repo-root `.env` (`override=True`, to beat the harness's empty env vars); the
  model is chosen by the harness. Providers: OpenAI, Anthropic (direct + OpenRouter + LiteLLM routing), Google.

## Gotchas & known issues (open-source cleanup noted these)

- **SysFlow is baked by MHBench, not installed here.** This repo only configures + starts it
  (`ansible/defender/sysflow/`). Don't re-add a SysFlow install step or vendor its `.deb`s.
- **Vulnerable `sudo` `.deb`s are not shipped** — the PE vuln playbooks expect them placed per
  `ansible/vulnerabilities/privledge_escalation/README.md`. `*.deb` is gitignored.
- **Server SSH keys are generated at setup** (`setup_ssh_keys.yml`), never committed.
- **`RestoreServer` has two safety guards** (`openstack_actuators/RestoreServer.py`): an allowlist
  (`_is_defendable_host`, primary, fails safe) + a `sensitive_subnets` denylist. Don't weaken these without
  reading the incident rationale in the file.
- **Config is "set only what you use".** Only the core runtime (`elastic_config`, `openstack_config`,
  `external_ip`, `experiment_timeout_minutes`) is required; the plugin/integration blocks
  (`incalmo_config`, `mhbench_config`, `caldera_config`, `llm_api_keys`) are optional.
- **Needs author attention** (flagged during OSS prep, not yet fixed):
  - `AttackerOnHost` event is defined/exported but emitted by nobody (dead).
  - `ReactiveStandalone` reads a restore budget into `max_restores` but never enforces it.
  - `llm_api_keys` in config vs `.env` — the LLM path reads `.env`; decide which is authoritative.

## Open-source status

Prepping for a public MIT release (see [LICENSE](LICENSE)). `deception`/`prompt_injection`-style strategies
are included. The public repo is produced as a **fresh-history snapshot** (the private history — which
contained a since-removed SSH key and vendored binaries — is not carried over).
