from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import TypeVar

from pydantic import BaseModel

from app.core.config import Settings
from app.services.llm import LLMClient

T = TypeVar("T", bound=BaseModel)


class AuditCostLimitReached(RuntimeError):
    """Raised before a model request would exceed the configured audit budget."""


class BudgetedLLMClient:
    def __init__(self, client: LLMClient, settings: Settings, current_cost: Callable[[], Decimal]) -> None:
        self.client = client
        self.settings = settings
        self.current_cost = current_cost

    def complete_json(self, system: str, prompt: str, schema: type[T]) -> T:
        schema_bytes = len(str(schema.model_json_schema()).encode("utf-8"))
        input_token_ceiling = len(system.encode("utf-8")) + len(prompt.encode("utf-8")) + schema_bytes + 512
        output_token_ceiling = self.settings.llm_max_output_tokens
        estimated_cost = (
            Decimal(input_token_ceiling) * self.settings.llm_input_usd_per_million
            + Decimal(output_token_ceiling) * self.settings.llm_output_usd_per_million
        ) / Decimal(1_000_000)
        # Reserve enough for the initial request plus the two invalid-JSON retries.
        estimated_cost *= 3
        if self.current_cost() + estimated_cost > self.settings.llm_max_cost_per_audit_usd:
            raise AuditCostLimitReached(
                f"The estimated next LLM call would exceed the ${self.settings.llm_max_cost_per_audit_usd} audit limit."
            )
        return self.client.complete_json(system, prompt, schema)
