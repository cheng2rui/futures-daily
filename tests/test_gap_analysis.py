from types import SimpleNamespace

from app.services.data_mart import pick_rows_by_source_priority
from app.services.gap_analysis import classify_archive, classify_external


def check() -> None:
    # Archive classifier: source limitations should be explicit; generic mapping
    # gap remains reserved for genuinely actionable archive misses.
    assert classify_archive("INE", "SC")["reason_code"] == "archive_source_not_covering_ine"
    assert classify_archive("CFFEX", "T")["reason_code"] == "archive_source_not_covering_financial"
    assert classify_archive("DCE", "M")["reason_code"] == "archive_mapping_or_source_gap"

    # External capability matrix: known non-coverage / not-applicable / inactive
    # cases should not be counted as generic actionable source gaps.
    assert classify_external("CFFEX", "IF", "basis")["reason_code"] == "external_not_applicable_financial"
    assert classify_external("CFFEX", "IF", "capital_flow")["reason_code"] == "external_source_gap"
    assert classify_external("GFEX", "SI", "capital_flow")["reason_code"] == "external_source_gap"
    assert classify_external("INE", "EC", "warehouse_receipt")["reason_code"] == "external_not_applicable_index"
    assert classify_external("CZCE", "JR", "capital_flow")["reason_code"] == "external_inactive_or_illiquid"
    assert classify_external("CZCE", "PL", "history_holding")["reason_code"] == "external_source_not_covering_new_variety"
    assert classify_external("CZCE", "AP", "basis")["reason_code"] == "external_source_not_covering_basis_sparse"
    assert classify_external("DCE", "JD", "warehouse_receipt")["reason_code"] == "external_source_not_covering_dce_warehouse"

    # Still-actionable example: no known capability limitation, so keep as real
    # external source gap for future source probing.
    assert classify_external("DCE", "JD", "capital_flow")["reason_code"] == "external_source_gap"

    # Quhe remains the preferred source when both Quhe and official fallback have
    # the same warehouse symbol; official rows are fallback-only supplements.
    picked = pick_rows_by_source_priority([
        SimpleNamespace(symbol="LC", source="akshare_official", value=1),
        SimpleNamespace(symbol="LC", source="quheqihuo", value=2),
        SimpleNamespace(symbol="PL", source="akshare_official", value=3),
    ], ["quheqihuo", "akshare_official"])
    assert picked["LC"].value == 2
    assert picked["PL"].value == 3

    basis_picked = pick_rows_by_source_priority([
        SimpleNamespace(symbol="FU", source="akshare_100ppi", value=1),
        SimpleNamespace(symbol="FU", source="quheqihuo", value=2),
        SimpleNamespace(symbol="PL", source="akshare_100ppi", value=3),
    ], ["quheqihuo", "akshare_100ppi"])
    assert basis_picked["FU"].value == 2
    assert basis_picked["PL"].value == 3


if __name__ == "__main__":
    check()
    print("ok")
