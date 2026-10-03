# Setup

Perry is driven by the experiment harness (see [architecture.md](architecture.md)), but it still needs its
own environment, config, and credentials. This page gets those in place.

## Prerequisites

- Python 3.11+ and a virtualenv.
- An **MHBench-deployed OpenStack range** to defend (Perry acts on it; it does not create it). The harness
  deploys the range and bakes the Glance images that decoys reuse.
- An **Elasticsearch** reachable from Perry, into which the range's Falco/SysFlow sensors ship telemetry.
  (In the standard setup the harness provides this per experiment.)
- LLM API key(s) if you run an LLM strategy (OpenAI / Anthropic / Google, or an OpenRouter / LiteLLM
  gateway).

## Install

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` is a hand-built manifest (this repo ships no native dependency file); its versions are
aligned with MHBench's so the same OpenStack / Ansible stack works against the same hosts.

## Configure

```bash
cp config/config_example.json config/config.json
```

Edit `config/config.json` — Elasticsearch, OpenStack, and (as needed) the range integration path and LLM
keys. Only the core runtime is required; the plugin/integration blocks are optional (set only what you
use). See [configuration.md](configuration.md) for the full field reference.

Put LLM API keys in a repo-root `.env` (gitignored) — copy [`.env.example`](../.env.example). The LLM
strategies read keys from `.env` (loaded with `override=True`), and the harness chooses the model.

## SSH keys

Nothing is shipped. Server SSH keys are generated on-host at setup time by
`ansible/.../setup_server_ssh_keys/setup_ssh_keys.yml`. Your OpenStack keypair for reaching the range is
configured via `openstack_config` in `config.json`.

## Running

There is no `python perry ...` command. In the standard flow the harness imports Perry, constructs a
`Defender` with its collaborators, and drives `prepare() → start() → run()` (see
[architecture.md](architecture.md) for the exact contract). If you are integrating Perry into your own
harness, that lifecycle is the integration point: build the five collaborators, then call those three
methods.

## Vulnerable-package note

The privilege-escalation vulns install specific old `sudo` `.deb`s that are **not** shipped in the repo.
If you use them, download each from a Debian archive and place it per
[`ansible/vulnerabilities/privledge_escalation/README.md`](../ansible/vulnerabilities/privledge_escalation/README.md).
