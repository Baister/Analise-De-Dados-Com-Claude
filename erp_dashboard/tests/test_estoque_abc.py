# tests/test_estoque_abc.py
import pandas as pd


# ── Lógica de zerados_lista (espelho de analisar_rapido) ─────────────

def _derive_zerados(df_criticos: pd.DataFrame) -> list:
    """Replica a derivação de zerados_lista do bot."""
    if df_criticos.empty or "QtdEstqDisp" not in df_criticos.columns:
        return []
    df_zer = df_criticos[df_criticos["QtdEstqDisp"].fillna(0) <= 0].copy()
    if df_zer.empty:
        return []
    if "DtUltVnd" in df_zer.columns:
        df_zer = df_zer.sort_values("DtUltVnd", na_position="last")
    keep = [c for c in ["CodItem", "DescrItem", "DescrMarca", "VlrEstq", "DtUltVnd"]
            if c in df_zer.columns]
    return df_zer[keep].to_dict("records")


def test_zerados_filtra_qtd_zero_e_negativo():
    df = pd.DataFrame({
        "CodItem":     ["A", "B", "C"],
        "DescrItem":   ["Prod A", "Prod B", "Prod C"],
        "DescrMarca":  ["M1", "M2", "M1"],
        "VlrEstq":     [100.0, 200.0, 50.0],
        "QtdEstqDisp": [10, 0, -1],
        "DtUltVnd":    pd.to_datetime(["2024-01-01", "2023-06-15", "2024-03-10"]),
    })
    result = _derive_zerados(df)
    assert len(result) == 2
    assert all(r["CodItem"] in ["B", "C"] for r in result)


def test_zerados_retorna_vazio_sem_QtdEstqDisp():
    df = pd.DataFrame({"CodItem": ["A"], "DescrItem": ["Produto"]})
    assert _derive_zerados(df) == []


def test_zerados_retorna_vazio_com_df_vazio():
    df = pd.DataFrame({"CodItem": [], "QtdEstqDisp": []})
    assert _derive_zerados(df) == []


def test_zerados_ordena_por_data_ascendente():
    df = pd.DataFrame({
        "CodItem":     ["A", "B"],
        "QtdEstqDisp": [0, 0],
        "DtUltVnd":    pd.to_datetime(["2024-06-01", "2023-01-01"]),
    })
    result = _derive_zerados(df)
    assert result[0]["CodItem"] == "B"   # mais antigo vem primeiro


def test_zerados_retorna_vazio_quando_todos_tem_estoque():
    df = pd.DataFrame({
        "CodItem":     ["A", "B"],
        "QtdEstqDisp": [5, 10],
        "DtUltVnd":    pd.to_datetime(["2024-01-01", "2024-01-02"]),
    })
    assert _derive_zerados(df) == []


# ── Lógica de classifyABC (espelho do utils/estoque.js) ─────────────

def _classify_abc(items: list, value_key: str = "val_vendido_90d") -> list:
    """Replica classifyABC do frontend: A=top 80%, B=80-95%, C=restante."""
    total = sum(r.get(value_key, 0) for r in items)
    if total == 0:
        return [{**r, "abc": "C"} for r in items]
    sorted_items = sorted(items, key=lambda r: r.get(value_key, 0), reverse=True)
    acc = 0.0
    result = []
    for r in sorted_items:
        acc += r.get(value_key, 0) / total
        acc_rounded = round(acc, 10)
        result.append({**r, "abc": "A" if acc_rounded <= 0.8 else ("B" if acc_rounded <= 0.95 else "C")})
    return result


def test_classify_abc_atribui_classes_corretas():
    items = [
        {"CodItem": "A", "val_vendido_90d": 800},
        {"CodItem": "B", "val_vendido_90d": 150},
        {"CodItem": "C", "val_vendido_90d": 30},
        {"CodItem": "D", "val_vendido_90d": 10},
        {"CodItem": "E", "val_vendido_90d": 10},
    ]
    result = _classify_abc(items)
    classes = {r["CodItem"]: r["abc"] for r in result}
    assert classes["A"] == "A"   # 80% sozinho → A
    assert classes["B"] == "B"   # 80–95% → B
    assert classes["C"] == "C"   # abaixo de 95% → C
    assert classes["D"] == "C"
    assert classes["E"] == "C"


def test_classify_abc_todos_C_quando_sem_vendas():
    items = [
        {"CodItem": "A", "val_vendido_90d": 0},
        {"CodItem": "B", "val_vendido_90d": 0},
    ]
    result = _classify_abc(items)
    assert all(r["abc"] == "C" for r in result)


def test_classify_abc_lista_vazia():
    assert _classify_abc([]) == []


def test_classify_abc_item_unico_e_C():
    result = _classify_abc([{"CodItem": "X", "val_vendido_90d": 500}])
    assert result[0]["abc"] == "C"


def test_classify_abc_preserva_campos_originais():
    items = [{"CodItem": "A", "val_vendido_90d": 100, "QtdEstq": 5}]
    result = _classify_abc(items)
    assert result[0]["QtdEstq"] == 5
