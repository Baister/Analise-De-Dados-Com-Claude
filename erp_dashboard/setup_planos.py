"""
setup_planos.py — apenas informativo
Mostra as condições de pagamento cadastradas (CodPlanoVnd).
NÃO é mais necessário executar antes do dashboard.
A separação Orçamento × Venda usa Blue.dbo.TbOrcPedVnd.OrcPedVnd.

    python setup_planos.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.database import db


def main():
    print("Conectando...")
    if not db.connect():
        print("ERRO: verifique config/settings.py")
        sys.exit(1)

    df = db.query("SELECT CodPlanoVnd, NomePlanoVnd FROM Blue.dbo.TbPlanoVnd ORDER BY CodPlanoVnd")
    if df.empty:
        print("Tabela TbPlanoVnd vazia ou nao encontrada.")
    else:
        print("\nCondições de pagamento cadastradas (CodPlanoVnd = forma de pagamento):")
        print("-" * 50)
        for _, row in df.iterrows():
            print(f"  Cod={row['CodPlanoVnd']}  Nome={row['NomePlanoVnd']}")

    df2 = db.query("""
        SELECT TOP 5
            OrcPedVnd,
            COUNT(*) AS qtd,
            CASE OrcPedVnd WHEN 1 THEN 'Orcamento' WHEN 2 THEN 'Venda Convertida' ELSE '?' END AS tipo
        FROM Blue.dbo.TbOrcPedVnd
        GROUP BY OrcPedVnd
    """)
    print("\nDistribuição geral TbOrcPedVnd:")
    print(df2.to_string(index=False))
    db.disconnect()


if __name__ == "__main__":
    main()
