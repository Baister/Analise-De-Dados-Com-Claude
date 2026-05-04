# core/exportador.py
# ─────────────────────────────────────────────
#  Exporta relatórios para Excel e CSV
# ─────────────────────────────────────────────

import pandas as pd
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

EXPORT_DIR = Path.home() / "ERP_Relatorios"


def exportar_excel(dados: dict, nome_bot: str) -> str:
    """Salva dados do bot em Excel formatado. Retorna o caminho do arquivo."""
    EXPORT_DIR.mkdir(exist_ok=True)
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = EXPORT_DIR / f"{nome_bot}_{ts}.xlsx"

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for chave, valor in dados.items():
            if isinstance(valor, list) and valor:
                df = pd.DataFrame(valor)
                sheet_name = chave[:31]  # Excel limita a 31 chars
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            elif not isinstance(valor, (list, dict)):
                # Dados escalares vão em uma aba "Resumo"
                pass

        # Aba de resumo com valores escalares
        resumo = {k: v for k, v in dados.items() if not isinstance(v, (list, dict))}
        if resumo:
            pd.DataFrame([resumo]).to_excel(writer, sheet_name="Resumo", index=False)

    logger.info("Exportado: %s", path)
    return str(path)


def exportar_csv(df: pd.DataFrame, nome: str) -> str:
    EXPORT_DIR.mkdir(exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = EXPORT_DIR / f"{nome}_{ts}.csv"
    df.to_csv(path, index=False, sep=";", encoding="utf-8-sig")
    logger.info("CSV exportado: %s", path)
    return str(path)
