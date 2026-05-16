from __future__ import annotations

import re
from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult

_CURRENCY_SYMBOLS: dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
}

_CURRENCY_PATTERN = re.compile(
    r"([€$£¥])\s*([\d,]+(?:\.\d+)?)|"
    r"([\d,]+(?:\.\d+)?)\s*(EUR|USD|GBP|JPY|eur|usd|gbp|jpy)",
)


def _normalize_currency(value: str) -> dict[str, Any] | None:
    m = _CURRENCY_PATTERN.search(value)
    if not m:
        return None
    if m.group(1):
        currency = _CURRENCY_SYMBOLS.get(m.group(1), m.group(1))
        amount = float(m.group(2).replace(",", ""))
    else:
        amount = float(m.group(3).replace(",", ""))
        currency = m.group(4).upper()
    return {"amount": amount, "currency": currency}


class NormalizeOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("normalize", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        data = config.get("data", {})
        normalized: dict[str, Any] = {}

        for key, value in data.items():
            if isinstance(value, str):
                parsed = _normalize_currency(value)
                if parsed:
                    normalized[key] = parsed
                else:
                    normalized[key] = value.strip()
            elif isinstance(value, list):
                normalized[key] = [
                    v.strip() if isinstance(v, str) else v for v in value
                ]
            else:
                normalized[key] = value

        return OperatorResult(
            success=True,
            data={"normalized": normalized},
            state_patch={"normalized_data": normalized},
        )
