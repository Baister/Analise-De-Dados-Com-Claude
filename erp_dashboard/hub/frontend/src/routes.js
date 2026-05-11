// routes.js — único arquivo a editar para adicionar novas abas.
// botKey: null para abas sem bot associado (relatórios estáticos, etc.)
export const ROUTES = [
  { key: 'dashboard',  label: 'Dashboard',  icon: '📊', botKey: 'dashboard',  component: () => import('./pages/Dashboard')  },
  { key: 'vendas',     label: 'Vendas',     icon: '💰', botKey: 'vendas',     component: () => import('./pages/Vendas')     },
  { key: 'estoque',    label: 'Estoque',    icon: '📦', botKey: 'estoque',    component: () => import('./pages/Estoque')    },
  { key: 'financeiro', label: 'Financeiro', icon: '💳', botKey: 'financeiro', component: () => import('./pages/Financeiro') },
  { key: 'crm',        label: 'CRM',        icon: '👥', botKey: 'crm',        component: () => import('./pages/CRM')        },
  { key: 'cliente',               label: 'Cliente',  icon: '🧾', botKey: null, component: () => import('./pages/Cliente')               },
  { key: 'cliente_comportamento', label: 'Clientes', icon: '👥', botKey: null, component: () => import('./pages/ClienteComportamento') },
];
