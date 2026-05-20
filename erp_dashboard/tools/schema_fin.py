"""Roda UMA VEZ para mapear colunas das views financeiras.
Uso: python tools/schema_fin.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import db

VIEWS = [
    "vmResumoDia",
    "vmCtRecResumo",
    "vmCtRecRecebido",
    "vmCtRecVinte",
    "vmCtRecTrinta",
    "vmCtRecDetalhe",
    "vmCtRecDocOriginal",
    "vmCtRecDocOriginalAbertoAte",
    "vmClientesComDebito",
    "vmClientesComDebitoDocs",
    "vmIndiceInadimplenciaGeral",
    "vmRecPagResumo",
    "vmReceberPagarRegCaixa",
    "vmCtPgDetalhe",
    "vmCtPgResumo",
    "vmCtPgVinte",
    "vwMovFinanc",
    "vwMovFinancCentroCusto",
    "vwMonitorNFE",
    "vmPainelPedidoVndConf",
    "vwPlanoVndCtRec",
]

for v in VIEWS:
    df = db.query(f"SELECT TOP 0 * FROM Blue.dbo.{v} WITH (NOLOCK)")
    if df is None or (df.empty and len(df.columns) == 0):
        print(f"\n[{v}] — ERRO ou vazia: {db.last_error}")
    else:
        print(f"\n[{v}]")
        for col in df.columns:
            print(f"  {col}")
