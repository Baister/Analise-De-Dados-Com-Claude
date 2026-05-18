import pandas as pd


def _run_groupby(df: pd.DataFrame) -> dict:
    _tim: dict = {}
    if not df.empty:
        for _mrc, _g in df.groupby("DescrMarca"):
            _tim[_mrc] = _g.nlargest(8, "faturamento")[
                ["DescrItem", "faturamento", "quantidade"]
            ].to_dict("records")
    return _tim


def test_top_itens_agrupa_por_marca():
    df = pd.DataFrame([
        {"DescrMarca": "CONDUTTI",  "DescrItem": "CABO 1,5MM", "faturamento": 200.0, "quantidade": 10},
        {"DescrMarca": "CONDUTTI",  "DescrItem": "CABO 2,5MM", "faturamento": 100.0, "quantidade":  5},
        {"DescrMarca": "HIKVISION", "DescrItem": "CAMERA IP",  "faturamento": 500.0, "quantidade":  2},
    ])
    result = _run_groupby(df)
    assert set(result.keys()) == {"CONDUTTI", "HIKVISION"}
    assert result["CONDUTTI"][0]["DescrItem"] == "CABO 1,5MM"
    assert result["CONDUTTI"][1]["DescrItem"] == "CABO 2,5MM"
    assert result["HIKVISION"][0]["DescrItem"] == "CAMERA IP"


def test_top_itens_limita_8_por_marca():
    rows = [
        {"DescrMarca": "MARCA_A", "DescrItem": f"Item{i}", "faturamento": float(100 - i), "quantidade": 1}
        for i in range(12)
    ]
    result = _run_groupby(pd.DataFrame(rows))
    assert len(result["MARCA_A"]) == 8
    assert result["MARCA_A"][0]["DescrItem"] == "Item0"


def test_top_itens_df_vazio_retorna_dict_vazio():
    df = pd.DataFrame(columns=["DescrMarca", "DescrItem", "faturamento", "quantidade"])
    assert _run_groupby(df) == {}


def test_top_itens_campos_presentes():
    df = pd.DataFrame([
        {"DescrMarca": "PPA", "DescrItem": "MOTOR PPA", "faturamento": 350.0, "quantidade": 3},
    ])
    result = _run_groupby(df)
    item = result["PPA"][0]
    assert "DescrItem"   in item
    assert "faturamento" in item
    assert "quantidade"  in item
