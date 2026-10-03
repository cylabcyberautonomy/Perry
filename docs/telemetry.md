# Telemetry

Perry turns raw host telemetry (Falco, SysFlow) into high-level **events** that strategies subscribe to.
Everything here is under `defender/telemetry/`.

## The bus — `TelemetryService`

A small pub/sub bus (`telemetry_service.py`):

- `subscribe(EventType, handler)` — a strategy registers a handler for an event type (usually in
  `initialize()`).
- `process_telemetry()` — called each `Defender.run()` tick: asks the analysis for new events and `emit()`s
  each to its subscribers (dispatched by exact event type).

## Ingestion — `TelemetryAnalysis`

The abstract base (`TelemetryAnalysis.py`) holds the Elasticsearch connection and the per-experiment
index names, and:

- creates the indices if absent (guards against a first-poll crash);
- `begin_monitoring()` stamps the scenario start; telemetry queries are floored at this time;
- `get_new_telemetry()` queries ES over a `now-180s` recency window (floored at the scenario start),
  dedupes already-seen records, `size=10000`, newest-first;
- `process_low_level_events()` (abstract) is where a subclass parses raw docs into `Event`s and emits them.

### Analysis implementations (pick the one that emits your strategy's events)

| Analysis | Emits | Notes |
|----------|-------|-------|
| `FalcoBasicAnalysis` | `FalcoEvent`; `SuspiciousHost` when a host exceeds **5** Falco alerts | For the LLM / prompt-injection strategies. |
| `FalcoAgressiveAnalysis` | same | Threshold **1** instead of 5. |
| `ReactiveCredentials` | `DecoyCredentialUsed`, `DecoyHostInteraction` | Richest decoy analysis; has an allowlist that suppresses the defender's own management/provisioning traffic (prevents self-triggered restores). |
| `SimpleTelemetryAnalysis` | `DecoyHostInteraction` | SysFlow network rules (netcat/curl to a decoy). |
| `NoTelemetry` | nothing | Never queries ES; for non-instrumented ranges. |

## Event types — `telemetry/events/`

All subclass a bare `Event`:

| Event | Carries | Emitted by |
|-------|---------|------------|
| `SuspiciousHost` | `host_name` | Falco analyses (over threshold) |
| `FalcoEvent` | `host_name` | Falco analyses (each alert) |
| `DecoyHostInteraction` | `source_ip`, `target_ip` | `SimpleTelemetryAnalysis`, `ReactiveCredentials` |
| `DecoyCredentialUsed` | `source_ip`, `decoy_user` | `ReactiveCredentials` |
| `AttackerOnHost` | `attacker_ip` | **nobody — defined but unused (dead); flagged for removal** |

`types/falco_alert.py` holds the `FalcoAlert` pydantic model parsed from ES docs.

## Per-experiment index scoping — `index_names.py`

Indices are `falco-<experiment_name>` / `sysflow-<experiment_name>`, resolved from `config.experiment_name`
(`config/config.py`). This matters: the Elasticsearch behind this is **shared and persistent**, and Falco /
SysFlow documents identify a host only by name/IP — both of which repeat across experiments. Without
per-experiment indices, one run's telemetry contaminates another's. The module docstring records the real
incident behind this. Keep the scoping.

## Writing an analysis

Subclass `TelemetryAnalysis`, implement `process_low_level_events()` to read the raw docs
`get_new_telemetry()` returned, build `Event`s, and `emit()` them. Then pair it with a strategy in your
harness so the strategy's subscribed handlers receive them.
