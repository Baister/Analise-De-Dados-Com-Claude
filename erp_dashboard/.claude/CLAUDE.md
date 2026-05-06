# CLAUDE.md — ERP Analytics Dashboard

> Lido automaticamente pelo Claude Code. Define comportamento obrigatório neste projeto.

---

## 🏗️ Contexto do Projeto

Aplicativo desktop Python (CustomTkinter) que conecta ao **SQL Server de produção** via DSN ODBC `blue_penha`.
Banco real: `Blue` | Schema: `dbo` | Prefixo obrigatório: `Blue.dbo.<objeto>`

**Stack:** Python 3.13 · pyodbc · pandas · CustomTkinter · matplotlib

---

## 🚨 REGRAS CRÍTICAS — NUNCA VIOLAR

### 1. Este banco é de PRODUÇÃO — erros são irreversíveis

O DSN `blue_penha` aponta para o banco real da empresa.
Não existe ambiente de testes separado. Qualquer dado apagado **não tem recuperação**.

### 2. Operações TOTALMENTE PROIBIDAS

Nunca gere, sugira ou execute — nem como exemplo:

| Proibido | Motivo |
|---|---|
| `DROP TABLE / VIEW / DATABASE` | Destruição permanente |
| `TRUNCATE TABLE` | Apaga todos os registros sem log |
| `DELETE` sem cláusula `WHERE` | Apaga tabela inteira |
| `ALTER TABLE` (remover colunas) | Perda estrutural irreversível |
| `UPDATE` sem cláusula `WHERE` | Modifica todos os registros |
| `EXEC xp_*` / `sp_*` do sistema | Acesso privilegiado ao servidor |

### 3. O método `db.query()` é somente leitura — mantenha assim

O `DatabaseManager` em `core/database.py` usa `autocommit=True` e só executa `SELECT`.
**Nunca adicione métodos de escrita (`INSERT`, `UPDATE`, `DELETE`) ao `DatabaseManager`.**
Se precisar de escrita no futuro, crie uma classe separada com confirmação explícita.

### 4. Credenciais visíveis em `config/settings.py` — não as exponha

O arquivo `config/settings.py` contém usuário e senha reais.
- ❌ Nunca imprima, faça log ou exiba `DB_CONFIG` completo
- ❌ Nunca leia ou modifique as credenciais
- ✅ Se precisar depurar conexão, use apenas `DB_CONFIG["dsn"]`

### 5. Queries devem sempre ter filtros específicos

```python
# ❌ NUNCA — sem filtro
df = db.query("SELECT * FROM Blue.dbo.TbProduto")

# ✅ SEMPRE — com filtro e LIMIT
df = db.query("SELECT TOP 100 * FROM Blue.dbo.TbProduto WHERE Ativo = 1")
```

### 6. Parada obrigatória para qualquer ação de risco

Se uma ação envolver modificação de dados, você **DEVE**:
1. Parar imediatamente
2. Descrever exatamente o que seria feito
3. Classificar o risco (BAIXO / MÉDIO / ALTO)
4. Aguardar confirmação explícita

---

## 📁 Estrutura do Projeto

```
erp_dashboard/
├── main.py                  ← Ponto de entrada
├── config/
│   └── settings.py          ← ⚠️ Contém credenciais — não modificar
├── core/
│   └── database.py          ← DatabaseManager (somente leitura)
├── bots/
│   └── analise_bots.py      ← 5 bots de análise (BaseBot + BotManager)
└── ui/
    └── app.py               ← Interface gráfica (ERPDashboard + 6 telas)
```

---

## ✅ Padrão Correto para Queries

Sempre use o singleton `db` já existente:

```python
from core.database import db

# Correto: SELECT com filtros e TOP
df = db.query("""
    SELECT TOP 500
        CodProduto,
        NomeProduto,
        QtdEstoque
    FROM Blue.dbo.TbProduto
    WHERE Ativo = 1
    ORDER BY NomeProduto
""")

if df.empty:
    print("Sem dados ou erro:", db.last_error)
```

---

## 📋 Formato de Resposta para Ações de Risco

```
📌 O que pretendo fazer:
[Descrição clara e específica]

⚠️ Classificação de risco: [BAIXO / MÉDIO / ALTO]

🔎 Impacto potencial:
[Quais tabelas/dados seriam afetados e de que forma]

✅ Aguardando sua confirmação explícita para prosseguir.
```

---

## 💡 Exemplo de Comportamento Esperado

**Usuário:** "apaga os clientes inativos do banco"

**Resposta correta:**
```
📌 O que pretendo fazer:
Executar DELETE em Blue.dbo.TbCliente filtrando clientes inativos.

⚠️ Classificação de risco: ALTO

🔎 Impacto potencial:
Remoção permanente de registros de clientes. Sem backup confirmado,
esses dados não podem ser recuperados. A tabela TbCliente pode ter
vínculos com TbVenda, TbTitulo e outras — deletar pode causar
erros de integridade referencial em todo o sistema.

Alternativa mais segura: UPDATE Blue.dbo.TbCliente SET Ativo = 0
WHERE <condição específica> — mantém o histórico intacto.

✅ Deseja prosseguir? Confirme explicitamente e informe o filtro exato.
```

---

## 🏆 Hierarquia de Valores

```
INTEGRIDADE DOS DADOS > Segurança > Completude > Velocidade
```
