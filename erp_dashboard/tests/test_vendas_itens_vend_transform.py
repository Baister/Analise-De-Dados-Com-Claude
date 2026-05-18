import pandas as pd


def _run_groupby_vend(df: pd.DataFrame) -> dict:
    _tiv: dict = {}
    if not df.empty:
        for _vnd, _g in df.groupby("Vendedor"):
            _tiv[_vnd] = _g.nlargest(8, "faturamento")[
                ["DescrItem", "faturamento", "quantidade"]
            ].to_dict("records")
    return _tiv


def test_top_itens_agrupa_por_vendedor():
    df = pd.DataFrame([
        {"Vendedor": "ANA",  "DescrItem": "CABO 1,5MM", "faturamento": 200.0, "quantidade": 10},
        {"Vendedor": "ANA",  "DescrItem": "CABO 2,5MM", "faturamento": 100.0, "quantidade":  5},
        {"Vendedor": "BRUNO", "DescrItem": "CAMERA IP",  "faturamento": 500.0, "quantidade":  2},
    ])
    result = _run_groupby_vend(df)
    assert set(result.keys()) == {"ANA", "BRUNO"}
    assert result["ANA"][0]["DescrItem"] == "CABO 1,5MM"
    assert result["ANA"][1]["DescrItem"] == "CABO 2,5MM"
    assert result["BRUNO"][0]["DescrItem"] == "CAMERA IP"


def test_top_itens_vend_limita_8_por_vendedor():
    rows = [
        {"Vendedor": "VEND_A", "DescrItem": f"Item{i}", "faturamento": float(100 - i), "quantidade": 1}
        for i in range(12)
    ]
    result = _run_groupby_vend(pd.DataFrame(rows))
    assert len(result["VEND_A"]) == 8
    assert result["VEND_A"][0]["DescrItem"] == "Item0"


def test_top_itens_vend_df_vazio_retorna_dict_vazio():
    df = pd.DataFrame(columns=["Vendedor", "DescrItem", "faturamento", "quantidade"])
    assert _run_groupby_vend(df) == {}


def test_top_itens_vend_campos_presentes():
    df = pd.DataFrame([
        {"Vendedor": "ANA", "DescrItem": "MOTOR PPA", "faturamento": 350.0, "quantidade": 3},
    ])
    result = _run_groupby_vend(df)
    item = result["ANA"][0]
    assert "DescrItem"   in item
    assert "faturamento" in item
    assert "quantidade"  in item
