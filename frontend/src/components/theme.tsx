// Shared Recharts theming for Fintrix — keeps every chart visually consistent
// with the glassmorphism / dark financial design system in index.css.

export const chartColors = {
  primary: "#3b82f6",
  primaryLight: "#60a5fa",
  accent: "#06b6d4",
  ai: "#8b5cf6",
  aiLight: "#a78bfa",
  success: "#10b981",
  warning: "#f59e0b",
  danger: "#ef4444",
  grid: "#1e3050",
  textMuted: "#7d8590",
  textDimmed: "#484f58",
};

/** Consistent dark glass tooltip for every chart — replaces Recharts' default
 * light-mode tooltip, which otherwise looks pasted-in against the app's dark cards. */
export function ChartTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: any[];
  label?: string;
  formatter?: (value: any, name: string) => [string, string];
}) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{
        background: "rgba(22,27,34,0.95)",
        border: "1px solid rgba(59,130,246,0.25)",
        backdropFilter: "blur(8px)",
        boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
      }}
    >
      {label && <p className="text-fintrix-text-dimmed mb-1 font-mono">{label}</p>}
      {payload.map((p, i) => {
        const [val, name] = formatter ? formatter(p.value, p.name) : [p.value, p.name];
        return (
          <div key={i} className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ background: p.color || p.fill }} />
            <span className="text-fintrix-text-muted">{name}:</span>
            <span className="text-fintrix-text font-mono font-medium">{val}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Shared gradient <defs> block — drop once at the top of any chart that uses
 * area/bar fills referencing these ids (e.g. fill="url(#gradPrimary)"). */
export function ChartGradients() {
  return (
    <defs>
      <linearGradient id="gradPrimary" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={chartColors.primary} stopOpacity={0.5} />
        <stop offset="100%" stopColor={chartColors.primary} stopOpacity={0.02} />
      </linearGradient>
      <linearGradient id="gradAccent" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={chartColors.accent} stopOpacity={0.5} />
        <stop offset="100%" stopColor={chartColors.accent} stopOpacity={0.02} />
      </linearGradient>
      <linearGradient id="gradAI" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={chartColors.ai} stopOpacity={0.6} />
        <stop offset="100%" stopColor={chartColors.ai} stopOpacity={0.05} />
      </linearGradient>
      <linearGradient id="barPrimary" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={chartColors.primaryLight} />
        <stop offset="100%" stopColor={chartColors.primary} />
      </linearGradient>
    </defs>
  );
}

export const axisTickStyle = { fill: chartColors.textMuted, fontSize: 10, fontFamily: "monospace" };
