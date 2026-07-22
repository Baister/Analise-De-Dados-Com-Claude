# Diagnóstico do CRM zerado — rodar NA MÁQUINA HUB:  python diagnostico_crm.py
# Executa as mesmas queries que alimentam funil/pipeline/taxa e mostra o erro real.
# Somente SELECT. Não imprime credenciais.
import sys, time, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

import pyodbc, pandas
print("=== AMBIENTE ===")
print("python :", sys.version.split()[0])
print("pyodbc :", pyodbc.version, "| pandas:", pandas.__version__)
print("drivers ODBC instalados:", [d for d in pyodbc.drivers() if "SQL" in d.upper()])

from core.database import db

def roda(nome, sql):
    t0 = time.time()
    df = db.new_conn_query(sql)
    el = time.time() - t0
    if df.empty:
        print(f"[FALHOU] {nome} em {el:.1f}s | erro: {db.last_error or '(vazio sem erro)'}")
    else:
        print(f"[OK]     {nome} em {el:.1f}s | {df.to_dict('records')[0]}")

print("\n=== TESTES (mesma janela do bot, GETDATE no servidor) ===")
roda("0. conexao/versao", "SELECT CAST(SERVERPROPERTY('ProductVersion') AS varchar(30)) AS sql_server")
roda("1. TRY_CAST suportado", "SELECT TRY_CAST('123' AS INT) AS try_cast_ok")
roda("2. TbOrcPedVnd do mes (contagem simples)", """
    SELECT COUNT(*) AS orcs_mes FROM Blue.dbo.TbOrcPedVnd o WITH (NOLOCK)
    WHERE o.OrcPedVnd IN (1, 2)
      AND o.DtOrcPedVnd >= DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0)
      AND o.DtOrcPedVnd <  DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, 0)
""")
roda("3. df_conv COMPLETA (a query que zera o funil)", """
    SELECT COUNT(*) AS total_orcamentos,
           COUNT(CASE WHEN o.OrcPedVnd = 2 THEN 1 END) AS total_convertidos,
           COUNT(CASE WHEN o.OrcPedVnd = 1 THEN 1 END) AS em_aberto,
           COUNT(nf.nr)                                  AS faturadas,
           SUM(CASE WHEN nf.nr IS NOT NULL
                    THEN o.ValTotalOrcPedVnd ELSE 0 END) AS valor_faturadas,
           SUM(CASE WHEN o.OrcPedVnd = 1 THEN o.ValTotalOrcPedVnd ELSE 0 END) AS valor_orcado
    FROM Blue.dbo.TbOrcPedVnd o WITH (NOLOCK)
    LEFT JOIN (SELECT DISTINCT TRY_CAST(n.NrOrcPedVnd AS INT) AS nr
               FROM Blue.dbo.TbNFVnd n WITH (NOLOCK)
               WHERE n.DataHoraCanc IS NULL AND n.Fat = 1
                 AND n.NrOrcPedVnd IS NOT NULL) nf
           ON nf.nr = TRY_CAST(o.NrOrcPedVnd AS INT)
    WHERE o.OrcPedVnd IN (1, 2)
      AND o.DtOrcPedVnd >= DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0)
      AND o.DtOrcPedVnd <  DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, 0)
""")
print("\nSe o teste 3 FALHOU e os demais passaram, copie a linha de erro e envie.")
