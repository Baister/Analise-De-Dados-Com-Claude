# ERP Analytics Dashboard
**Aplicativo desktop de análise métrica — Python + SQL Server**

---

## ⚡ Instalação rápida

### 1. Pré-requisitos
- Python 3.10+
- [ODBC Driver 17 for SQL Server](https://learn.microsoft.com/pt-br/sql/connect/odbc/download-odbc-driver-for-sql-server) instalado na máquina cliente

### 2. Instalar dependências
```bash
pip install -r requirements.txt
```

### 3. Configurar conexão
Abra **`config/settings.py`** e ajuste:
```python
DB_CONFIG = {
    "server":   "192.11.10.10",      # ← IP do servidor (já configurado)
    "database": "ERP_DB",             # ← nome real do seu banco
    "user":     "",                   # ← deixe vazio para Windows Auth
    "password": "",
}
```

### 4. Executar
```bash
python main.py
```

---

## 🗂️ Estrutura de arquivos

```
erp_dashboard/
├── main.py                  ← Ponto de entrada
├── requirements.txt
├── config/
│   └── settings.py          ← IP, banco, intervalos, alertas
├── core/
│   ├── database.py          ← Conexão única compartilhada (não sobrecarrega)
│   └── exportador.py        ← Exportação Excel/CSV
├── bots/
│   └── analise_bots.py      ← 5 bots de análise automática
└── ui/
    └── app.py               ← Interface gráfica (CustomTkinter)
```

---

## 🤖 Bots e intervalos padrão

| Bot         | Intervalo | O que analisa |
|-------------|-----------|---------------|
| Vendas      | 5 min     | Total do dia/mês, pedidos, ticket médio, meta, histórico 7d |
| Estoque     | 10 min    | Críticos, zerados, valor total, por categoria |
| Financeiro  | 15 min    | A receber/pagar, inadimplência, top devedores |
| Produção    | 10 min    | Ordens abertas, atrasadas, eficiência, por setor |
| Clientes    | 30 min    | Total, ativos, novos 30d, top compradores 90d |

Intervalos configuráveis em `config/settings.py → BOT_INTERVALS`.

---

## 🔧 Adaptar às tabelas do seu banco

As queries estão em **`bots/analise_bots.py`**.  
Cada bot tem um comentário com as tabelas/colunas esperadas. Exemplo:

```python
class BotVendas(BaseBot):
    """
    Tabelas esperadas:
      PEDIDOS       — PedidoID, DataPedido, ValorTotal, Status, ClienteID, VendedorID
      ITENS_PEDIDO  — PedidoID, ProdutoID, Qtd, PrecoUnit
    """
```

Basta trocar os nomes de tabelas/colunas nas queries SQL para bater com seu ERP.

---

## 🛡️ Proteção do servidor

- **Conexão única compartilhada** — todos os bots usam a mesma conexão via `ThreadLock`
- **Intervalos longos** — queries rodam de 5 a 30 minutos conforme o módulo
- **`TOP N` em todas as queries** — nunca traz mais que `ALERTAS["query_max_rows"]` linhas (padrão: 5.000)
- **Timeout configurável** — conexão abandona após `DB_CONFIG["timeout"]` segundos
- **Reconexão automática** — em caso de queda de rede, reconecta silenciosamente

---

## 📤 Exportação

Clique em **"⬇ Exportar Excel"** na barra inferior para salvar os dados da aba ativa.  
Os arquivos são salvos em: `C:\Users\<usuário>\ERP_Relatorios\`

---

## 🖥️ Requisitos de hardware (mínimo)
- CPU: qualquer dual-core
- RAM: 512 MB livres
- Rede: acesso ao gateway `192.11.10.10` na porta 1433 (SQL Server padrão)
