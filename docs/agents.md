# LLM agents

The LLM strategies (`FalcoLLM`, `FalcoLLMC2Block`) use the agent layer in `defender/agents/` to triage a
suspicious host and decide whether to restore it or block its C2. Everything rides LangChain.

## Model registry — `langchain_registry.py`

`LangChainRegistry` resolves a model name to a LangChain chat model. Two ways to name a model:

- **Fixed table** — named OpenAI (`gpt-4`, `gpt-4o`, `gpt-4o-mini`, `o1`, …), Anthropic (`claude-3-opus`,
  `claude-3.5-sonnet`, `claude-3.7-sonnet`, …), and Google (`gemini-1.5-pro`, `gemini-2.5-pro`, …) models.
- **Dynamic routing prefixes:**
  - `openrouter/<slug>` — via OpenRouter (cost read from the response body).
  - `litellm/<name>` — via a LiteLLM gateway (cost captured from the `x-litellm-response-cost` header).
  - `anthropic/<model>` — Anthropic first-party direct (`max_tokens=8192`, no temperature; cost computed
    from a built-in per-MTok price table).

API keys load from a repo-root `.env` with `override=True` (so an empty var exported by the harness doesn't
shadow a real key). The harness chooses which model a run uses.

## Conversation wrapper — `llm_agent.py`

`LLMAgent` wraps a model as a conversation: `send_message(...)`, tag extraction (`extract_tag`,
`is_finished` on a `<finished>` tag), per-call token/cost logging to `token_usage.json`, served-model
capture, and flattening of Anthropic block-list content to text.

## Investigation agent — `agents/sysflow/`

`SysFlowAgent` runs a bounded investigation loop (`QUERY_BUDGET = 5`) against the run's scoped SysFlow
index, and returns a `SysFlowAgentReport` (`malware_confirmed`, `c2c_ip`). Its system prompt depends on the
job:

- `preprompt.txt` — C2 identification (used by `FalcoLLMC2Block`, `identify_c2=True`).
- `preprompt_restore.txt` — restore-only triage (used by `FalcoLLM`, `identify_c2=False`).

So `FalcoLLM` restores a host when the agent returns `malware_confirmed`; `FalcoLLMC2Block` additionally
blocks the reported `c2c_ip`.

## Cost / token logging — `token_logger.py`

`TokenUsageLogger` writes an Incalmo-shaped `token_usage.json` (tokens + cost per call). Cost comes from
the provider response (OpenRouter body / LiteLLM header) or is computed from the built-in Anthropic price
table for the direct route.
