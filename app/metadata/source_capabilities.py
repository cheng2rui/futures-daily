from __future__ import annotations

from dataclasses import dataclass


EXTERNAL_SIGNAL_KINDS = {"capital_flow", "basis", "warehouse_receipt", "history_holding"}

# Varieties that are inactive, suspended, TAS-only, or structurally low-liquidity
# in the current daily universe. Missing optional/enhancement data for these should
# not be treated as actionable source gaps.
COLD_OR_INACTIVE = {
    "DCE": {"BZ", "FB", "BB", "LG"},
    "CZCE": {"JR", "LR", "PM", "RI", "WH", "ZC", "RS"},
    "SHFE": {"WR", "SC_TAS"},
    "GFEX": {"PD", "PT"},
    "INE": {"SC_TAS"},
}

# Probed-empty symbols for Quhe history/seat endpoints. These are known source
# limitations rather than mapping bugs.
THIRD_PARTY_EMPTY = {
    "INE": {"BC", "EC", "SC", "SC_TAS"},
    "GFEX": {"PD", "PT"},
}

# External signal source capability matrix for Quhe enhancements.
# Values are intentionally conservative: only mark non-actionable when the current
# source is known not to cover a product class or when the signal is not meaningful.
SOURCE_NOT_COVERING = {
    "capital_flow": {},
    "basis": {
        "CZCE": {"AP", "CJ", "PK"},
        "DCE": {"B", "CS", "RR"},
        "SHFE": {"AD", "AO", "OP"},
        "INE": {"BC", "EC", "LU", "NR", "SC", "SC_TAS"},
    },
    "warehouse_receipt": {
        "DCE": {"EB", "JD"},
        "INE": {"EC"},
    },
    "history_holding": {
        "CFFEX": {"IC", "IF", "IH", "IM", "T", "TF", "TL", "TS"},
        "CZCE": {"PL", "PR"},
        "GFEX": {"PS"},
        "SHFE": {"AD", "OP"},
    },
}

NOT_APPLICABLE = {
    "basis": {
        "CFFEX": {"IC", "IF", "IH", "IM", "T", "TF", "TL", "TS"},
    },
    "warehouse_receipt": {
        "CFFEX": {"IC", "IF", "IH", "IM", "T", "TF", "TL", "TS"},
        # Shipping index has no physical warehouse receipt semantics.
        "INE": {"EC"},
    },
}

ARCHIVE_SOURCE_NOT_COVERING = {
    "CFFEX": {"IC", "IF", "IH", "IM", "T", "TF", "TL", "TS"},
    "INE": {"BC", "EC", "NR", "SC", "SC_TAS"},
}


@dataclass(frozen=True)
class CapabilityReason:
    code: str
    text: str
    actionable: bool

    def as_dict(self) -> dict[str, object]:
        return {"reason_code": self.code, "reason": self.text, "actionable": self.actionable}


def is_cold_or_inactive(exchange: str, symbol: str) -> bool:
    return symbol.upper() in COLD_OR_INACTIVE.get(exchange, set())


def is_third_party_empty(exchange: str, symbol: str) -> bool:
    return symbol.upper() in THIRD_PARTY_EMPTY.get(exchange, set())


def classify_archive_capability(exchange: str, symbol: str) -> CapabilityReason | None:
    symbol = symbol.upper()
    if symbol in ARCHIVE_SOURCE_NOT_COVERING.get(exchange, set()):
        if exchange == "CFFEX":
            return CapabilityReason("archive_source_not_covering_financial", "rsstsx 结构化归档主要覆盖商品期货，金融期货结构信号缺失属预期。", False)
        if exchange == "INE":
            return CapabilityReason("archive_source_not_covering_ine", "rsstsx 结构化归档当前基本不覆盖 INE 这些能源/航运/国际品种。", False)
    if is_cold_or_inactive(exchange, symbol):
        return CapabilityReason("archive_inactive_or_illiquid", "冷门/低流动性品种未进入结构化归档。", False)
    return None


def classify_external_capability(exchange: str, symbol: str, kind: str) -> CapabilityReason | None:
    symbol = symbol.upper()
    if kind not in EXTERNAL_SIGNAL_KINDS:
        return None

    if is_cold_or_inactive(exchange, symbol):
        return CapabilityReason("external_inactive_or_illiquid", "冷门/停用/低流动性品种，第三方增强源通常不覆盖。", False)

    if symbol in NOT_APPLICABLE.get(kind, {}).get(exchange, set()):
        if exchange == "CFFEX":
            return CapabilityReason("external_not_applicable_financial", "金融期货通常没有基差/仓单类商品数据。", False)
        if exchange == "INE" and kind == "warehouse_receipt":
            return CapabilityReason("external_not_applicable_index", "指数类品种没有仓单类实物交割数据。", False)
        return CapabilityReason("external_not_applicable", f"{kind} 对该品种不适用。", False)

    if kind == "history_holding" and is_third_party_empty(exchange, symbol):
        return CapabilityReason("external_third_party_empty", "曲合历史持仓接口对该品种为空。", False)

    if symbol in SOURCE_NOT_COVERING.get(kind, {}).get(exchange, set()):
        if exchange == "CFFEX":
            return CapabilityReason("external_source_not_covering_financial", f"曲合 {kind} 当前不覆盖中金所金融期货。", False)
        if exchange == "INE":
            return CapabilityReason("external_source_not_covering_ine", f"曲合 {kind} 当前不覆盖该 INE 品种。", False)
        if kind == "history_holding":
            return CapabilityReason("external_source_not_covering_new_variety", "曲合历史多空持仓当前未沉淀该新品种/新合约。", False)
        if kind == "basis":
            return CapabilityReason("external_source_not_covering_basis_sparse", "当前曲合/100ppi 基差源均未覆盖该品种，需后续寻找新的现货/基差源。", False)
        if kind == "warehouse_receipt" and exchange == "DCE":
            return CapabilityReason("external_source_not_covering_dce_warehouse", "曲合与当前 AkShare/DCE 官方仓单通道均未覆盖该 DCE 品种。", False)
        if exchange == "GFEX":
            return CapabilityReason("external_source_not_covering_gfex", f"曲合 {kind} 当前不覆盖该 GFEX 品种。", False)
        return CapabilityReason("external_source_not_covering", f"曲合 {kind} 当前不覆盖该品种。", False)

    return None
