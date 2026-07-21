# G2 Analytics — Dashboard Analítico para ERP Blue

Plataforma de BI operacional que conecta ao SQL Server do ERP **Blue** (somente leitura) e entrega análises de vendas, estoque, financeiro, CRM, impostos e clientes em tempo quase-real — via **dashboard web espelhável na rede local** e aplicativo desktop.

> ⚠️ O banco é de **produção**: toda a camada de dados é estritamente `SELECT` (`WITH (NOLOCK)`), sem qualquer operação de escrita no ERP.

---

## Arquitetura

**Hub-and-spoke + camadas.** Uma única máquina (hub) conversa com o SQL Server; as demais acessam pelo navegador.

```
┌────────────────────────── HUB (1 máquina) ──────────────────────────┐
│  Bots (threads, ciclos de 5–30 min)                                 │
│  ├─ 2 fases de consultas PARALELAS (ThreadPoolExecutor, 4 workers)  │
│  └─ pré-agregam payloads por dimensão (vendedor/marca/situação)     │
│           │ resultado em memória + cache SQLite (WAL)               │
│  FastAPI ─┼─ /dados/{bot} (servido da RAM) · /dados/cliente (360º)  │
│           ├─ /auth (perfis → abas) · /metas · /stream (SSE)         │
│           └─ /app → build React estático (Vite)                     │
└───────────────┬─────────────────────────────────────────────────────┘
                │ HTTP na LAN
   Navegadores (React SPA)          Desktop (CustomTkinter)
   filtros 100% client-side         consome os mesmos bots
```

**Decisões-chave**

- **Bots agendados** (Template Method + Observer): cada aba tem um bot que consulta, agrega e publica um payload; SSE notifica o front, que refaz o fetch.
- **Leitura quente da memória**: `GET /dados/{bot}` responde da RAM do hub com serialização idêntica ao cache; SQLite (journal **WAL**) é fallback e persistência entre restarts.
- **Filtros client-side**: o bot pré-agrega por vendedor/marca e o navegador apenas troca a fonte — filtragem instantânea, zero roundtrip.
- **RBAC por perfil**: senha → conjunto de abas; o backend bloqueia (`403`) dados fora do perfil — não é só visual.
- **Consulta sob demanda** onde faz sentido: o Cliente 360º roda 7 queries paralelas por cliente (~4 s), sem bot.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | **Python 3.13** · **FastAPI** + Uvicorn · pyodbc (ODBC Driver 18 / DSN) · pandas |
| Dados | **SQL Server** (ERP Blue, somente leitura) · **SQLite** (cache local, WAL) |
| Frontend | **React 18** · **Vite** · **Tailwind CSS** · **Recharts** |
| Desktop | CustomTkinter + matplotlib |
| Tempo real | Server-Sent Events (SSE) + polling de fallback |

## Funcionalidades (8 abas)

- **Dashboard** — KPIs financeiros do mês (fórmulas DAX portadas), meta dinâmica por dias úteis, filtros instantâneos
- **Vendas** — resultado comercial, progresso diário vs metas individuais, **Ritmo do Mês** (acumulado × meta)
- **Estoque** — Curva ABC, giro/cobertura, estoque parado (R$ imobilizado), evolução reconstruída + snapshots diários
- **Financeiro** — contas a receber, inadimplência %, foco Boleto/Cartão com drill-down, limite de crédito
- **CRM** — funil, ranking de vendedores, orçamentos abertos (aging), clientes novos/risco/inativos
- **Imposto** — ICMS/CFOP do livro fiscal (`Fat=1`, validado 100% contra o BI de referência), projeção do mês
- **Cliente 360º** — busca + perfil completo: o que compra, vendedores, títulos, orçamentos
- **Configurações** — metas mensal e individuais (formato BR)

## Como executar

```bash
# Pré-requisitos no hub: Python 3.13, ODBC Driver 18, DSN "blue_penha" configurado
pip install -r requirements.txt        # fastapi, uvicorn, pyodbc, pandas...
cd erp_dashboard/hub/frontend && npm install && npm run build   # gera hub/static
cd ../.. && python hub/run_hub.py      # ou duplo-clique em INICIAR_HUB.bat
# Acesso: http://<ip-do-hub>:8765/app  (login por senha de perfil)
```

## Estrutura

```
erp_dashboard/
├── hub/            # FastAPI (server.py), runner e build React (frontend/ → static/)
├── bots/           # análise: 6 bots + BotManager (analise_bots.py)
├── core/           # DatabaseManager (somente leitura) e CacheManager (SQLite/WAL)
├── config/         # settings, perfis de acesso, metas.json
└── ui/             # aplicativo desktop
```

## Qualidade e engenharia

Cada aba possui um guia de continuidade interno (fontes de dados, fórmulas e armadilhas conhecidas), todas as métricas foram **validadas contra relatórios de referência (Power BI)** antes de entrar no ar, e o projeto passou por **auditoria multi-agente com verificação adversarial** — dezenas de bugs confirmados e corrigidos antes do deploy. Todos os bots registram a duração dos ciclos; consultas pesadas rodam paralelizadas em conexões independentes. *(Docs internos e valores de negócio ficam fora do repositório por confidencialidade.)*

---

*Projeto interno — credenciais e perfis de acesso são definidos em `config/settings.py` (não versionar senhas reais em forks públicos).*
