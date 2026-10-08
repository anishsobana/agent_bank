"""Money helpers: Indian digit grouping and JSON-safe conversion of domain objects."""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any


def inr(value: float | Decimal) -> str:
    """Format with Indian grouping: 1234567 -> '12,34,567'."""
    v = float(value)
    digits = str(round(abs(v)))
    if len(digits) > 3:
        head, last3 = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + last3
    return ("-" if v < 0 else "") + digits


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses / Decimal / datetime / Enum into JSON-friendly values."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        if hasattr(obj, "is_debit"):
            out["is_debit"] = obj.is_debit
        return out
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat(timespec="seconds") if isinstance(obj, datetime) else obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k.value if isinstance(k, Enum) else k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    return obj
