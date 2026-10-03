# Architecture

## Run model: a library driven by a harness

Perry is the **defender side** of an MHBench experiment. It is a **library** — it has no CLI, no `main`,
and no run loop of its own. An external **harness** (the "arena", with lineage from MHBench / Incalmo):

- constructs a `Defender` and its five collaborators,
- drives the `prepare → start → run` lifecycle (the run loop lives in the harness),
- selects the strategy and the LLM model,
- deploys the OpenStack range and bakes the images decoys reuse,
- owns the Elasticsearch that Falco/SysFlow telemetry ships into,
- gates the attacker on the defender's readiness.

So "use Perry" means: the harness imports it and drives a `Defender`. The contract below is what the
harness relies on; it's also what you'd implement if you drive Perry yourself.

## The Defender lifecycle

`Defender(arsenal, strategy, telemetry_service, orchestrator, network)` — `defender/Defender.py`. Three
methods, called in this order:

```text
# (constructed and driven by the harness)
defender.prepare()              # external arming, BEFORE the scenario, in a setup process
defender.start(prepared=True)   # in-process wiring, in the scenario-loop process
while running:                  # the loop lives in the harness
    defender.run()              # one tick
```

- **`prepare()`** — runs `strategy.initialize()` **iff** `strategy.ARMS_IN_SETUP` is True. This is for
  slow, failure-prone external arming (deploying decoy VMs, planting honey credentials): doing it in a
  separate setup step means it finishes — and fails loudly — before the attacker is released, instead of
  racing inside the loop. No-op for strategies that don't arm in setup.
- **`start(prepared)`** — if the strategy armed in `prepare()` (`ARMS_IN_SETUP` + `prepared=True`), it does
  **not** re-run `initialize()` (decoy deploy isn't idempotent). For a non-arming strategy it runs
  `initialize()` here. Either way it then calls `begin_monitoring()` to stamp the scenario start time
  (telemetry queries are floored at this timestamp).
- **`run()`** — one tick: `telemetry_service.process_telemetry()` then `strategy.run()`.

### `ARMS_IN_SETUP`

A strategy sets `ARMS_IN_SETUP = True` only when its `initialize()` is **pure external arming** — no
telemetry subscriptions, no in-process state the loop reads (its `run()` is inert). The static decoy /
honey-credential planters are the arming strategies; the reactive, LLM, and dynamic prompt-injection
strategies leave it False because their `initialize()` also wires up subscriptions / builds maps that
their event handlers consume.

## Per-tick pipeline

Each `run()` tick flows one direction — telemetry in, actions out:

1. **Pull.** `process_telemetry()` → `TelemetryAnalysis.get_new_telemetry()` queries the per-experiment
   Elasticsearch indices (`falco-<exp>` / `sysflow-<exp>`) for records since the scenario start.
2. **Parse.** `process_low_level_events()` turns raw Falco/SysFlow docs into high-level `Event`s
   (`SuspiciousHost`, `DecoyCredentialUsed`, …).
3. **Emit.** Each event is published on the `TelemetryService` pub/sub bus to the strategy's subscribed
   handlers.
4. **Decide.** The strategy's handler builds `Action` dataclasses (from `capabilities/`).
5. **Act.** `OpenstackOrchestrator` dispatches each action to its actuator, which executes it on the range
   via the OpenStack SDK + Ansible.

Most strategies act in their **event handlers** (registered via `telemetry_service.subscribe(EventType,
handler)` during `initialize()`), not in `run()`. See [telemetry.md](telemetry.md) for the event types and
which analysis emits them, [strategies.md](strategies.md) for the decision layer, and
[responses.md](responses.md) for the action layer.

## Components

| Component | Role |
|-----------|------|
| `Defender` | The lifecycle object; wires telemetry-in to strategy to actions-out each tick. |
| `Strategy` | The decision policy. Subscribes to events; dispatches actions. |
| `TelemetryService` + `TelemetryAnalysis` | Pub/sub bus + the Falco/SysFlow→Events ingestion (pick the analysis that emits the events your strategy needs). |
| `OpenstackOrchestrator` + actuators | Executes response actions on the range. |
| `Network` | Topology/inventory the strategy reasons over (subnets, hosts). |
| `Arsenal` | The per-run action budget/inventory. |
| `agents/` | LLM wiring used by the LLM strategies (SOC triage, C2 identification). |

## Lineage

Derived from an internal research framework; shares patterns with **Incalmo** (the attacker side) — the
`token_usage.json` shape, the `LangChainRegistry`, the `.env override=True` convention. The harness that
drives it is MHBench / the arena.
