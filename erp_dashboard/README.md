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
├── main.py                  ← Ponto de entrada (app desktop)
├── requirements.txt
├── config/
│   ├── settings.py          ← IP, banco, intervalos, alertas (⚠️ credenciais reais)
│   └── metas.json           ← Metas mensais por vendedor (gerado pela UI)
├── core/
│   ├── database.py          ← Conexão única compartilhada (somente leitura)
│   └── cache.py             ← Cache de resultados em disco
├── bots/
│   └── analise_bots.py      ← 6 bots de análise automática
├── hub/
│   ├── server.py            ← FastAPI — API REST + SSE
│   ├── run_hub.py           ← Entry point do hub web
│   └── frontend/src/        ← React + Vite (buildar antes de testar)
└── ui/
    └── app.py               ← Interface desktop (CustomTkinter) — modo legado
```

**Hub web:** `python hub/run_hub.py` → abrir `http://localhost:8765/app`  
**Após mudar qualquer arquivo `.jsx`/`.js`:** `cd hub/frontend && npm run build`

---

## 🤖 Bots e abas do hub web

| Bot / Aba | O que analisa |
|-----------|---------------|
| Dashboard | KPIs globais, top vendedores, faturamento diário, meta do dia, marcas |
| Vendas | Faturamento por marca/grupo/vendedor, devoluções, **progresso de metas mensais e diárias** |
| Estoque | Críticos, zerados, valor total, giro por marca |
| Financeiro | A receber, inadimplência, tipos de recebimento |
| CRM | Funil de orçamentos, conversão, clientes inativos |
| Cliente | Histórico de compras por cliente |
| **Configurações** | Definir meta mensal total e metas individuais por vendedor |

### Metas de Vendedores

Na aba **Configurações**, o gestor pode:
1. Definir a meta mensal total
2. Clicar "Distribuir igualmente" para dividir entre todos os vendedores
3. Ajustar individualmente e salvar

Os dados são salvos em `config/metas.json` (sem escrita no banco).

Na aba **Vendas**, uma seção de progresso colorida mostra:
- **Mensal:** % atingida por vendedor no mês (verde ≥100%, amarelo ≥70%, vermelho <70%)
- **Diário:** vendas de hoje vs. meta diária (meta_mensal ÷ dias úteis do mês)

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
