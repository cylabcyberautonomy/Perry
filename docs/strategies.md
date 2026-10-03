# Strategies

A **strategy** is the decision policy: it arms the environment (decoys, honey credentials) and/or
subscribes to telemetry events and dispatches response actions. Strategies live in `defender/strategy/`;
the harness selects one by name (there is no in-repo name→class registry).

## The `Strategy` interface

Subclass `Strategy` (`defender/strategy/Strategy.py`):

```python
class Strategy(ABC):
    ARMS_IN_SETUP: bool = False      # see below

    def __init__(self, arsenal, network, orchestrator, telemetry_service, llm_model=None): ...

    @abstractmethod
    def initialize(self): ...         # arm before the scenario: deploy decoys / plant creds,
                                      # and/or telemetry_service.subscribe(EventType, handler)

    def run(self): ...               # called each loop tick; default no-op
```

Helpers on the base: `_honeycred_deploy_hosts(count)` (round-robin over the entry subnet),
`_defended_host_count()`, `_default_decoy_count()` (~⅓ of defended hosts, floor 1).

**`ARMS_IN_SETUP`** — set it `True` only when `initialize()` is *pure external arming*: it deploys
decoys/credentials and nothing else (no subscriptions, no in-process state the loop reads, `run()` inert).
Those strategies arm in `Defender.prepare()` (a setup process, before the attacker). Strategies that also
subscribe to events or build maps their handlers read must leave it `False` (they arm in `start()`). See
[architecture.md](architecture.md).

## Catalog

### Baseline
- **`DoNothing`** — does nothing (control).

### Static decoy / honey-credential (arm in setup)
These pre-place deception, then do nothing reactive. All are `ARMS_IN_SETUP = True`.

- **`NaiveDecoyCredential`** — N non-real honey credentials split evenly across every subnet.
- **`NaiveDecoyHost`** — decoys (prefers `webserver_network`), then fake data on each.
- **`StaticStandalone`** — decoys on `webserver_network` + non-real honey creds across subnets.
- **`StaticLayered`** — random-subnet decoys + fake data + **real** honey creds on the entry path.

### Reactive (respond to decoy interaction)
Leave `ARMS_IN_SETUP = False` (they arm + subscribe).

- **`ReactiveLayered`** — decoys + real honey creds; subscribes to `DecoyCredentialUsed` /
  `DecoyHostInteraction`; restores compromised / planting / decoy hosts with a 60s per-host cooldown
  (`RESTORE_COOLDOWN_SECONDS`), no restore cap.
- **`ReactiveStandalone`** — decoys + non-real creds; restores source/target on decoy events. *Note: reads
  a restore budget into `max_restores` but does not currently enforce it.*

### Prompt-injection decoys
Deploy decoys whose names / users / file names / file contents carry prompt-injection payloads aimed at an
LLM attacker.

- **`StaticLayeredAll`** (`All.py`) — all four channels, static (`ARMS_IN_SETUP = True`).
- **`StaticLayeredHostName` / `StaticLayeredUserName` / `StaticLayeredFileName` / `StaticLayeredFileContent`**
  — single-channel ablations (each `ARMS_IN_SETUP = True`).
- **`AIAttackerDetection`** (`dynamic_prompt_injection.py`) — dynamic: subscribes to `FalcoEvent`; after ≥3
  Falco events in a 120s window, deploys 5 decoys with a honey SSH service + all-channel injection.

### LLM SOC (`strategy/llm/`)
- **`FalcoLLM`** — on `SuspiciousHost`, dispatches a `SysFlowAgent` (LLM) on a thread pool to triage, and
  restores the host only on `malware_confirmed`.
- **`FalcoLLMC2Block`** — same, but also identifies the C2 and blocks its IP (`BlockIP(c2c_ip, 8888)`) on
  confirmed malware.

### Test
- **`FalcoTest`** — logs `SuspiciousHost` events, takes no actions.

## Pairing a strategy with telemetry

A strategy only receives the events its paired **telemetry analysis** emits (the harness pairs them):

- LLM / prompt-injection strategies need a **Falco** analysis (`SuspiciousHost` / `FalcoEvent`).
- Reactive strategies need a **decoy-event** analysis (`DecoyCredentialUsed` / `DecoyHostInteraction`).
- Static arming strategies need no telemetry; pair with `NoTelemetry` on non-instrumented ranges.

See [telemetry.md](telemetry.md).

## Adding a strategy

1. Subclass `Strategy`; implement `initialize()` (arm and/or `subscribe`) and, if reactive-per-tick,
   `run()`.
2. Set `ARMS_IN_SETUP` correctly (pure-arming → `True`).
3. Build response actions as capability dataclasses and dispatch them via `self.orchestrator`
   (see [responses.md](responses.md)).
4. Export it from `defender/strategy/__init__.py` and wire its name in your harness's selection.
