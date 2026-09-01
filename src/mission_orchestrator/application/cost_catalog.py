from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


CATALOG_VERSION = "o5-v1"


@dataclass(frozen=True)
class CostRecord:
    served_provider: str
    served_model: str
    input_tokens: int
    output_tokens: int
    estimated_usd: float | None
    known: bool
    catalog_version: str


@dataclass
class CostLedger:
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_usd: float = 0.0
    known: bool = True

    def add(self, record: CostRecord) -> None:
        self.input_tokens += record.input_tokens
        self.output_tokens += record.output_tokens
        if record.estimated_usd is None:
            self.known = False
        else:
            self.estimated_usd += record.estimated_usd

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def budget_exceeded(self, token_budget: int | None) -> bool:
        return token_budget is not None and self.total_tokens > token_budget


def cost_record(
    served_provider: str | None,
    served_model: str | None,
    input_tokens: int,
    output_tokens: int,
    catalog: Mapping[tuple[str, str], tuple[float, float]],
) -> CostRecord:
    provider, model = served_provider or "unknown", served_model or "unknown"
    price = catalog.get((provider, model))
    if price is None:
        return CostRecord(provider, model, input_tokens, output_tokens, None, False, CATALOG_VERSION)
    total = (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000
    return CostRecord(provider, model, input_tokens, output_tokens, round(total, 6), True, CATALOG_VERSION)
