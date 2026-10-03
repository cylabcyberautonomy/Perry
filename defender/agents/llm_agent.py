import os
import time

from .langchain_registry import LangChainRegistry
from .token_logger import TokenUsageLogger, header_float
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

try:
    from utility.logging import PerryLogger, log_event
except Exception:  # pragma: no cover
    PerryLogger = None
    log_event = None


class LLMAgent:
    def __init__(self, preprompt: str, model_name: str = "claude-3.7-sonnet"):
        self.registry = LangChainRegistry()
        self.model_name = model_name
        self.model = self.registry.get_model(model_name)
        self.preprompt = preprompt

        self.conversation: list[SystemMessage | HumanMessage | AIMessage] = [
            SystemMessage(content=self.preprompt),
        ]

        self.max_message_len = 30000

        self._step = 0
        self._header_client = self.registry.get_header_client(model_name)
        self.token_logger = self._make_token_logger()

        # Model id the provider actually resolved to (the requested slug may differ).
        self._served_model: str | None = None
        self._served_model_logged = False

    def _make_token_logger(self) -> TokenUsageLogger | None:
        out_dir = getattr(PerryLogger, "output_dir", None) if PerryLogger else None
        if not out_dir:
            return None
        try:
            return TokenUsageLogger(os.path.join(out_dir, "token_usage.json"))
        except Exception:
            return None

    def _record_usage(self, response, latency_ms: float | None = None) -> None:
        """Extract token counts and cost from an invoke() response and log one row."""
        if self.token_logger is None:
            return
        try:
            self._step += 1
            meta = getattr(response, "response_metadata", None) or {}
            usage = getattr(response, "usage_metadata", None) or {}
            itd = usage.get("input_token_details") or {}
            otd = usage.get("output_token_details") or {}
            token_usage = meta.get("token_usage") or {}
            cost = token_usage.get("cost")
            litellm_cost = None
            if self._header_client is not None:
                litellm_cost = header_float(
                    self._header_client.last_headers(), "x-litellm-response-cost"
                )
                if cost is None:
                    cost = litellm_cost
            # Compute cost from token counts when the provider reports none.
            if cost is None:
                cost = self.registry.estimate_cost(self.model_name, usage)
            self.token_logger.record(
                call_type="defender_sysflow",
                model=self.model_name,
                step=self._step,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=itd.get("cache_read", 0),
                cache_creation_tokens=(
                    (itd.get("cache_creation") or 0)
                    + (itd.get("ephemeral_5m_input_tokens") or 0)
                    + (itd.get("ephemeral_1h_input_tokens") or 0)
                ),
                reasoning_tokens=otd.get("reasoning", 0),
                response_id=meta.get("id") or getattr(response, "id", None),
                wall_clock_latency_ms=latency_ms,
                cost=cost,
                # langchain-anthropic reports "model_provider" instead of "provider".
                provider=meta.get("provider") or meta.get("model_provider"),
                finish_reason=meta.get("finish_reason") or meta.get("stop_reason"),
                prompt_tokens=usage.get("input_tokens"),
                completion_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
                litellm_response_cost=litellm_cost,
                served_model=self._served_model,
            )
        except Exception:
            pass

    def _log_served_model(self, response) -> None:
        """Capture and log the model id the provider actually served."""
        try:
            meta = getattr(response, "response_metadata", None) or {}
            served = meta.get("model_name") or meta.get("model")
            if served:
                self._served_model = served
            provider = meta.get("provider") or meta.get("model_provider")
            if not self._served_model_logged and log_event is not None:
                log_event(
                    "LLMAgent",
                    f"served_model={served} provider={provider} "
                    f"(requested={self.model_name})",
                )
                self._served_model_logged = True
        except Exception:
            pass

    def send_message(self, message: str) -> str:
        if len(message) > self.max_message_len:
            message = message[: self.max_message_len]
            message += "\n[Message truncated to fit within the max length]"

        self.conversation.append(HumanMessage(content=message))

        start = time.monotonic()
        response = self.model.invoke(self.conversation)
        latency_ms = (time.monotonic() - start) * 1000

        self._log_served_model(response)
        self._record_usage(response, latency_ms)

        response_content = self._content_to_text(response.content)

        self.conversation.append(AIMessage(content=response_content))

        return response_content

    @staticmethod
    def _content_to_text(content) -> str:
        """Flatten a LangChain message's `content` to plain text."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    # Keep text blocks. Skip thinking and tool blocks that have no answer text.
                    if item.get("type", "text") in ("text", "output_text") and item.get("text"):
                        parts.append(item["text"])
            return "".join(parts)
        return str(content)

    def get_last_message(self) -> str:
        return self._content_to_text(self.conversation[-1].content)

    def is_finished(self) -> bool:
        return "<finished>" in self.conversation[-1].content

    def extract_tag(self, message: str, tag: str) -> str | None:
        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"

        start = message.find(start_tag)
        end = message.find(end_tag)

        if start == -1 or end == -1:
            return None

        return message[start + len(start_tag) : end]

    def save_conversation(self, filename: str):
        with open(filename, "w") as file:
            file.write(self.conversation_to_string())

    def conversation_to_string(self):
        conversation = ""
        for message in self.conversation:
            if isinstance(message, SystemMessage):
                role = "system"
            elif isinstance(message, HumanMessage):
                role = "user"
            elif isinstance(message, AIMessage):
                role = "assistant"
            else:
                role = "unknown"

            conversation += f"{role}: {message.content}\n\n"
        return conversation

    def get_preprompt(self) -> str:
        return self.preprompt
