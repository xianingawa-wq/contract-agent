from __future__ import annotations


CONTRACT_TYPE_ALIASES: dict[str, str] = {
    "purchase": "采购合同",
    "procurement": "采购合同",
    "general": "通用合同",
    "common": "通用合同",
}


def normalize_contract_type(contract_type: str | None, *, default: str = "通用合同") -> str:
    if contract_type is None:
        return default
    normalized = contract_type.strip()
    if not normalized:
        return default
    return CONTRACT_TYPE_ALIASES.get(normalized.lower(), normalized)
