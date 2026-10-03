import os
import threading
from pathlib import Path

import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Dict, Callable, Any


class _HeaderCapturingHTTPClient(httpx.Client):
    """httpx.Client that stores each response's raw HTTP headers in thread-local storage."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tls = threading.local()

    def send(self, request, **kwargs):
        response = super().send(request, **kwargs)
        self._tls.headers = dict(response.headers)
        return response

    def last_headers(self) -> Dict[str, str]:
        return getattr(self._tls, "headers", {})

# override=True so this .env wins over an inherited empty ANTHROPIC_API_KEY.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

_OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")


class LangChainRegistry:
    def __init__(self):
        self._model_factories = {
            "gpt-4": lambda: ChatOpenAI(model="gpt-4", temperature=0.7),
            "gpt-4o": lambda: ChatOpenAI(model="gpt-4o", temperature=0.7),
            "gpt-4o-mini": lambda: ChatOpenAI(model="gpt-4o-mini", temperature=0.7),
            "gpt-3.5-turbo": lambda: ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7),
            "gpt-o1": lambda: ChatOpenAI(model="o1-preview", temperature=0.7),
            "claude-3-opus": lambda: ChatAnthropic(
                model_name="claude-3-opus-latest",
                temperature=0.7,
                timeout=60,
                stop=None,
            ),
            "claude-3-sonnet": lambda: ChatAnthropic(
                model_name="claude-3-sonnet-latest",
                temperature=0.7,
                timeout=60,
                stop=None,
            ),
            "claude-3-haiku": lambda: ChatAnthropic(
                model_name="claude-3-haiku-latest",
                temperature=0.7,
                timeout=60,
                stop=None,
            ),
            "claude-3.5-sonnet": lambda: ChatAnthropic(
                model_name="claude-3-5-sonnet-latest",
                temperature=0.7,
                timeout=60,
                stop=None,
            ),
            "claude-3.5-haiku": lambda: ChatAnthropic(
                model_name="claude-3-5-haiku-latest",
                temperature=0.7,
                timeout=60,
                stop=None,
            ),
            "claude-3.7-sonnet": lambda: ChatAnthropic(
                model_name="claude-3-7-sonnet-latest",
                temperature=0.7,
                timeout=60,
                stop=None,
            ),
            "claude-3.7-thinking": lambda: ChatAnthropic(
                model_name="claude-3-7-thinking-latest",
                temperature=0.7,
                timeout=60,
                stop=None,
            ),
            "gemini-1.5-pro": lambda: ChatGoogleGenerativeAI(
                model="gemini-1.5-pro", temperature=0.7
            ),
            "gemini-1.5-flash": lambda: ChatGoogleGenerativeAI(
                model="gemini-1.5-flash", temperature=0.7
            ),
            "gemini-2.5-pro": lambda: ChatGoogleGenerativeAI(
                model="gemini-2.5-pro", temperature=0.7
            ),
            "gemini-2-flash": lambda: ChatGoogleGenerativeAI(
                model="gemini-2-flash", temperature=0.7
            ),
        }

        self._models: Dict[str, Any] = {}
        # http clients for litellm models, keyed by prefix-stripped model name.
        self._header_clients: Dict[str, Any] = {}

    def _build_openrouter(self, model_slug: str):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is not set (checked .env at the repo root and "
                "the environment) - required for openrouter/<model> models."
            )
        # usage.include makes OpenRouter return the call cost in response.usage.
        return ChatOpenAI(
            model=model_slug,
            api_key=api_key,
            base_url=_OPENROUTER_BASE_URL,
            temperature=0.7,
            extra_body={"usage": {"include": True}},
        )

    def _build_litellm(self, model_name: str):
        api_key = os.environ.get("LITELLM_API_KEY")
        base_url = os.environ.get("LITELLM_BASE_URL")
        if not api_key or not base_url:
            raise ValueError(
                "LITELLM_API_KEY and/or LITELLM_BASE_URL are not set (checked .env "
                "at the repo root and the environment) - both required for "
                "litellm/<model> models."
            )
        # Header-capturing client so the gateway's x-litellm-response-cost header is readable after invoke().
        client = _HeaderCapturingHTTPClient()
        model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7,
            http_client=client,
        )
        self._header_clients[model_name] = client
        return model

    def _build_anthropic(self, model_slug: str):
        """Direct first-party Anthropic model (ChatAnthropic), keyed by ANTHROPIC_API_KEY."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set (checked .env at the repo root and "
                "the environment) - required for anthropic/<model> models. Add a "
                "funded key (sk-ant-...) to the deception repo's .env."
            )
        return ChatAnthropic(
            model_name=model_slug,
            api_key=api_key,
            timeout=60,
            max_tokens=8192,
            stop=None,
        )

    def get_model(self, model_name: str):
        """Get or create a model instance by name."""
        if model_name in self._models:
            return self._models[model_name]

        if model_name.startswith("openrouter/"):
            model = self._build_openrouter(model_name[len("openrouter/"):])
        elif model_name.startswith("litellm/"):
            model = self._build_litellm(model_name[len("litellm/"):])
        elif model_name.startswith("anthropic/"):
            model = self._build_anthropic(model_name[len("anthropic/"):])
        elif model_name in self._model_factories:
            model = self._model_factories[model_name]()
        else:
            raise ValueError(
                f"Model {model_name!r} not found. Available fixed models: "
                f"{', '.join(self._model_factories.keys())}. Or use an "
                f"'openrouter/<model-slug>', 'litellm/<model-name>', or "
                f"'anthropic/<model>' prefix."
            )

        self._models[model_name] = model
        return model

    # First-party Anthropic list prices, USD per 1M tokens (input, output).
    _ANTHROPIC_PRICES_PER_MTOK = {
        "claude-sonnet-5": (2.00, 10.00),
        "claude-sonnet-4-5": (3.00, 15.00),
        "claude-sonnet-4-5-20250929": (3.00, 15.00),
        "claude-opus-5": (5.00, 25.00),
        "claude-haiku-4-5": (1.00, 5.00),
    }

    def estimate_cost(self, model_name: str, usage: dict) -> float | None:
        """Dollar cost of one call from token counts, or None if the model is not priced."""
        slug = model_name[len("anthropic/"):] if model_name.startswith("anthropic/") else model_name
        price = self._ANTHROPIC_PRICES_PER_MTOK.get(slug)
        if not price or not usage:
            return None
        in_p, out_p = price
        itd = usage.get("input_token_details") or {}
        input_tokens = usage.get("input_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or 0
        cache_read = itd.get("cache_read", 0) or 0
        # Price a cache write by TTL. Use the generic key at the 5-minute rate if no TTL split is present.
        write_5m = itd.get("ephemeral_5m_input_tokens", 0) or 0
        write_1h = itd.get("ephemeral_1h_input_tokens", 0) or 0
        if not (write_5m or write_1h):
            write_5m = itd.get("cache_creation", 0) or 0
        base_input = max(input_tokens - cache_read - write_5m - write_1h, 0)
        cost = (
            base_input * in_p
            + cache_read * in_p * 0.1
            + write_5m * in_p * 1.25
            + write_1h * in_p * 2.0
            + output_tokens * out_p
        ) / 1_000_000
        return cost

    def get_header_client(self, model_name: str):
        """Return the header-capturing http client for a litellm model, or None."""
        key = model_name[len("litellm/"):] if model_name.startswith("litellm/") else model_name
        return self._header_clients.get(key)
