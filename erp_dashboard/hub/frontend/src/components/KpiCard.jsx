const COLORS = {
  default: '#e6edf3',
  success: '#238636',
  warning: '#d29922',
  error:   '#da3633',
};

export default function KpiCard({ label, value, sub, variant = 'default' }) {
  return (
    <div className="bg-card border border-card_border rounded-lg p-4 flex-1 min-w-[120px]">
      <p className="text-subtext text-[10px] uppercase tracking-wider mb-1.5">{label}</p>
      <p className="text-xl font-bold" style={{ color: COLORS[variant] }}>{value ?? '—'}</p>
      {sub && <p className="text-subtext text-[10px] mt-1">{sub}</p>}
    </div>
  );
}
