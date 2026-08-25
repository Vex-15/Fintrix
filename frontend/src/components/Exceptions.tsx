import { useState, useEffect, useCallback } from "react";
import { api, type ExceptionItem, type DeepInvestigation } from "../api";

function formatINR(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

// ── Severity Badge ───────────────────────────────────────────────────────────
function SeverityBadge({ severity }: { severity: string }) {
  const styles: Record<string, string> = {
    low: "bg-slate-500/12 text-slate-400 border-slate-500/25",
    medium: "bg-amber-500/12 text-amber-400 border-amber-500/25",
    high: "bg-orange-500/12 text-orange-400 border-orange-500/25",
    critical: "bg-red-500/12 text-red-400 border-red-500/25",
  };
  return (
    <span className={`px-2 py-0.5 rounded-md border text-[11px] font-semibold uppercase tracking-wider ${styles[severity] || styles.medium}`}>
      {severity}
    </span>
  );
}

// ── Status Badge ─────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    detected: "bg-amber-500/12 text-amber-400 border-amber-500/25",
    investigating: "bg-blue-500/12 text-blue-400 border-blue-500/25",
    resolved: "bg-emerald-500/12 text-emerald-400 border-emerald-500/25",
    escalated: "bg-red-500/12 text-red-400 border-red-500/25",
  };
  const icons: Record<string, string> = {
    detected: "◌",
    investigating: "⟳",
    resolved: "✓",
    escalated: "⚑",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-[11px] font-semibold ${styles[status] || ""}`}>
      <span>{icons[status] || "?"}</span>
      {status}
    </span>
  );
}

// ── Confidence Meter ─────────────────────────────────────────────────────────
function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.85 ? "from-emerald-500 to-emerald-400" :
    value >= 0.65 ? "from-amber-500 to-yellow-400" :
    "from-red-500 to-red-400";
  const glowColor =
    value >= 0.85 ? "rgba(16,185,129,0.3)" :
    value >= 0.65 ? "rgba(245,158,11,0.3)" :
    "rgba(239,68,68,0.3)";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-fintrix-text-muted">AI Confidence</span>
        <span className="text-sm font-bold font-mono">{pct}%</span>
      </div>
      <div className="confidence-meter">
        <div
          className={`confidence-fill bg-gradient-to-r ${color}`}
          style={{ width: `${pct}%`, boxShadow: `0 0 12px ${glowColor}` }}
        />
      </div>
      <p className="text-[10px] text-fintrix-text-dimmed">
        {value >= 0.85 ? "✓ High confidence — eligible for auto-resolve" :
         value >= 0.65 ? "⚠ Moderate — needs human approval" :
         "✗ Low confidence — escalated"}
      </p>
    </div>
  );
}

// ── Comparison Table ─────────────────────────────────────────────────────────
function ComparisonTable({ comparison }: { comparison: DeepInvestigation["comparison"] }) {
  if (!comparison) return null;

  const rows = [
    {
      label: "Gross Amount",
      txn: comparison.transaction_side.gross_amount,
      setl: comparison.settlement_side?.amount ?? null,
      bank: comparison.bank_side?.credit ?? null,
    },
    {
      label: "Fees",
      txn: comparison.transaction_side.fees,
      setl: comparison.settlement_side?.fees ?? null,
      bank: null,
    },
    {
      label: "Tax",
      txn: comparison.transaction_side.tax,
      setl: comparison.settlement_side?.tax ?? null,
      bank: null,
    },
    {
      label: "Refunds",
      txn: comparison.transaction_side.refunds,
      setl: null,
      bank: null,
    },
    {
      label: "Net Amount",
      txn: comparison.transaction_side.net_amount,
      setl: comparison.settlement_side?.amount ?? null,
      bank: comparison.bank_side?.credit ?? null,
    },
  ];

  return (
    <div className="overflow-hidden rounded-lg border border-fintrix-border">
      <table className="w-full">
        <thead>
          <tr className="bg-fintrix-surface-2/50 text-[11px] text-fintrix-text-muted uppercase tracking-wider">
            <th className="text-left px-4 py-2.5 font-medium">Field</th>
            <th className="text-right px-4 py-2.5 font-medium">Transaction</th>
            <th className="text-right px-4 py-2.5 font-medium">Settlement</th>
            <th className="text-right px-4 py-2.5 font-medium">Bank</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const mismatch = (row.setl !== null && row.txn !== row.setl) ||
              (row.bank !== null && row.setl !== null && row.setl !== row.bank);
            return (
              <tr key={row.label} className={`border-t border-fintrix-border/50 ${mismatch ? "bg-fintrix-danger/5" : ""}`}>
                <td className="px-4 py-2 text-xs text-fintrix-text-muted">{row.label}</td>
                <td className="px-4 py-2 text-xs font-mono text-right">{row.txn !== null ? formatINR(row.txn) : "—"}</td>
                <td className={`px-4 py-2 text-xs font-mono text-right ${mismatch ? "text-fintrix-danger font-semibold" : ""}`}>
                  {row.setl !== null ? formatINR(row.setl) : "—"}
                </td>
                <td className={`px-4 py-2 text-xs font-mono text-right ${mismatch ? "text-fintrix-danger font-semibold" : ""}`}>
                  {row.bank !== null ? formatINR(row.bank) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Investigation Timeline ───────────────────────────────────────────────────
function InvestigationTimeline({ timeline }: { timeline: DeepInvestigation["timeline"] }) {
  if (!timeline.length) return null;

  const actorClasses: Record<string, string> = {
    system: "timeline-node-system",
    ai_investigator: "timeline-node-ai",
    human: "timeline-node-human",
  };

  const actorLabels: Record<string, string> = {
    system: "⚙️ System",
    ai_investigator: "🤖 AI",
    human: "👤 Human",
  };

  return (
    <div className="relative">
      <div className="timeline-line" />
      {timeline.map((entry, i) => (
        <div key={entry.id} className={`timeline-node ${actorClasses[entry.actor] || "timeline-node-system"}`}>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[11px] font-medium">{actorLabels[entry.actor] || entry.actor}</span>
            <span className="text-[10px] text-fintrix-text-dimmed font-mono">
              {new Date(entry.timestamp).toLocaleTimeString()}
            </span>
          </div>
          <p className="text-xs text-fintrix-text-muted capitalize">{entry.action.replace(/_/g, " ")}</p>
          {entry.new_state && (
            <div className="mt-1.5 text-[11px] font-mono text-fintrix-text-dimmed bg-fintrix-surface-2/50 rounded px-2 py-1">
              {Object.entries(entry.new_state).slice(0, 3).map(([k, v]) => (
                <span key={k} className="mr-3">
                  <span className="text-fintrix-text-muted">{k}:</span> {typeof v === "object" ? "..." : String(v)}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Deep Investigation Drawer ────────────────────────────────────────────────
function DeepInvestigationDrawer({
  exceptionId,
  onClose,
  onAction,
}: {
  exceptionId: number;
  onClose: () => void;
  onAction: (id: number, action: string) => void;
}) {
  const [data, setData] = useState<DeepInvestigation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getDeepInvestigation(exceptionId)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [exceptionId]);

  if (loading) {
    return (
      <div className="glass-card p-8 animate-shimmer">
        <div className="text-center text-fintrix-text-muted">
          <p className="text-sm animate-pulse">Loading deep investigation...</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="glass-card p-8 text-center text-fintrix-text-muted">
        <p className="text-sm">Failed to load investigation data</p>
      </div>
    );
  }

  const exc = data.exception;
  const inv = data.investigation;

  return (
    <div className="glass-card overflow-y-auto max-h-[calc(100vh-140px)] animate-slide-in-right">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-fintrix-surface/90 backdrop-blur-md border-b border-fintrix-border p-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold">Exception #{exc.id}</h3>
              <StatusBadge status={exc.status} />
              <SeverityBadge severity={exc.severity} />
            </div>
            <p className="text-sm text-fintrix-text-muted mt-1 capitalize">
              {exc.type.replace(/_/g, " ")}
            </p>
          </div>
          <div className="text-right">
            <p className="text-lg font-bold gradient-text-warm">{formatINR(exc.amount_at_risk)}</p>
            <button
              onClick={onClose}
              className="mt-1 text-xs text-fintrix-text-muted hover:text-fintrix-text transition-colors cursor-pointer"
            >
              ✕ Close
            </button>
          </div>
        </div>
      </div>

      <div className="p-5 space-y-6">
        {/* ── Comparison Table ─────────────────── */}
        {data.comparison && (
          <div>
            <h4 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-3">
              Transaction vs Settlement vs Bank
            </h4>
            <ComparisonTable comparison={data.comparison} />
          </div>
        )}

        {/* ── AI Investigation Report ─────────── */}
        {inv && (
          <div className="border border-fintrix-primary/20 rounded-xl p-5 bg-fintrix-primary/5 space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-lg">🧠</span>
              <h4 className="text-sm font-bold text-fintrix-primary">AI Investigation Report</h4>
              {inv.model_used && (
                <span className="text-[10px] text-fintrix-text-muted ml-auto font-mono bg-fintrix-surface-2/50 px-2 py-0.5 rounded">
                  {inv.model_used} · {inv.latency_ms}ms
                </span>
              )}
            </div>

            {/* Root Cause */}
            <div>
              <p className="text-[11px] text-fintrix-text-muted uppercase tracking-wider mb-1.5">Root Cause</p>
              <p className="text-sm font-medium">{inv.root_cause}</p>
            </div>

            {/* Evidence */}
            <div>
              <p className="text-[11px] text-fintrix-text-muted uppercase tracking-wider mb-2">Evidence</p>
              <div className="space-y-2">
                {(inv.evidence.points || []).map((e, i) => (
                  <div key={i} className="flex gap-2 text-sm text-fintrix-text-muted bg-fintrix-surface/50 rounded-lg p-2.5">
                    <span className="text-fintrix-accent shrink-0 mt-0.5">›</span>
                    <span>{e}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Confidence */}
            <ConfidenceMeter value={inv.confidence} />

            {/* Recommendation */}
            <div className="flex items-center gap-3 p-3 rounded-lg bg-fintrix-surface/50 border border-fintrix-border-subtle">
              <div>
                <p className="text-[10px] text-fintrix-text-muted uppercase tracking-wider">Recommended Action</p>
                <p className="text-sm font-semibold capitalize mt-0.5">
                  {inv.recommended_action.replace(/_/g, " ")}
                </p>
              </div>
              {inv.resolution_type && (
                <div className="ml-auto text-right">
                  <p className="text-[10px] text-fintrix-text-muted">Resolution</p>
                  <p className="text-xs font-medium text-fintrix-text capitalize">{inv.resolution_type} · {inv.resolved_by}</p>
                </div>
              )}
            </div>

            {/* Agent Decision Trace */}
            {inv.agent_decision_trace && (
              <div className="mt-4 pt-4 border-t border-fintrix-border-subtle">
                <p className="text-[11px] text-fintrix-text-muted uppercase tracking-wider mb-2">Agent Decision Trace</p>
                <div className="bg-fintrix-surface-2/50 rounded-lg p-3 border border-fintrix-border-subtle text-xs font-mono text-fintrix-text-muted max-h-48 overflow-y-auto">
                  <pre className="whitespace-pre-wrap">{JSON.stringify(inv.agent_decision_trace, null, 2)}</pre>
                </div>
              </div>
            )}

            {/* Human Feedback */}
            <div className="flex items-center gap-3 pt-2">
              <span className="text-[11px] text-fintrix-text-muted uppercase tracking-wider">Feedback:</span>
              <button 
                onClick={async () => {
                  try {
                    await api.addFeedback(exc.id, "helpful");
                    setData(prev => prev ? { ...prev, investigation: { ...prev.investigation!, user_feedback: "helpful" } } : prev);
                  } catch (e) {
                    console.error(e);
                  }
                }}
                className={`px-3 py-1 text-xs border rounded-lg cursor-pointer transition-colors ${inv.user_feedback === "helpful" ? "bg-fintrix-success/20 border-fintrix-success/50 text-fintrix-success" : "border-fintrix-border text-fintrix-text-muted hover:text-fintrix-text hover:bg-fintrix-surface-2"}`}
              >
                👍 Helpful
              </button>
              <button 
                onClick={async () => {
                  try {
                    await api.addFeedback(exc.id, "unhelpful");
                    setData(prev => prev ? { ...prev, investigation: { ...prev.investigation!, user_feedback: "unhelpful" } } : prev);
                  } catch (e) {
                    console.error(e);
                  }
                }}
                className={`px-3 py-1 text-xs border rounded-lg cursor-pointer transition-colors ${inv.user_feedback === "unhelpful" ? "bg-fintrix-danger/20 border-fintrix-danger/50 text-fintrix-danger" : "border-fintrix-border text-fintrix-text-muted hover:text-fintrix-text hover:bg-fintrix-surface-2"}`}
              >
                👎 Unhelpful
              </button>
            </div>
          </div>
        )}

        {/* ── Context ─────────────────────────── */}
        <div>
          <h4 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-3">
            Raw Context
          </h4>
          <div className="bg-fintrix-surface-2/50 rounded-lg p-4 border border-fintrix-border-subtle">
            <pre className="text-[11px] font-mono text-fintrix-text-muted overflow-x-auto whitespace-pre-wrap leading-relaxed">
              {JSON.stringify(exc.context, null, 2)}
            </pre>
          </div>
        </div>

        {/* ── Related Records ─────────────────── */}
        {data.transaction_records.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-3">
              Related Transactions ({data.transaction_records.length})
            </h4>
            <div className="space-y-2">
              {data.transaction_records.map((txn) => (
                <div key={txn.id} className="bg-fintrix-surface-2/30 rounded-lg p-3 border border-fintrix-border-subtle text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-medium text-fintrix-text">{txn.id}</span>
                    <span className="font-mono text-fintrix-warning">{formatINR(txn.amount)}</span>
                  </div>
                  <div className="flex gap-4 mt-1.5 text-fintrix-text-muted">
                    <span>Type: {txn.type}</span>
                    <span>Method: {txn.method || "—"}</span>
                    <span>Fee: {formatINR(txn.fee)}</span>
                    <span>Status: {txn.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Timeline ────────────────────────── */}
        {data.timeline.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-3">
              Investigation Timeline
            </h4>
            <InvestigationTimeline timeline={data.timeline} />
          </div>
        )}

        {/* ── Action Buttons ──────────────────── */}
        {(exc.status === "escalated" || exc.status === "detected") && (
          <div className="flex gap-3 pt-2 border-t border-fintrix-border">
            <button
              onClick={() => onAction(exc.id, "approve")}
              className="flex-1 px-4 py-2.5 bg-fintrix-success/12 text-fintrix-success border border-fintrix-success/25 rounded-xl text-sm font-semibold hover:bg-fintrix-success/20 transition-all cursor-pointer"
            >
              ✓ Approve & Resolve
            </button>
            <button
              onClick={() => onAction(exc.id, "escalate")}
              className="px-4 py-2.5 bg-fintrix-warning/12 text-fintrix-warning border border-fintrix-warning/25 rounded-xl text-sm font-semibold hover:bg-fintrix-warning/20 transition-all cursor-pointer"
            >
              ⚑ Escalate
            </button>
            <button
              onClick={() => onAction(exc.id, "reject")}
              className="px-4 py-2.5 bg-fintrix-danger/12 text-fintrix-danger border border-fintrix-danger/25 rounded-xl text-sm font-semibold hover:bg-fintrix-danger/20 transition-all cursor-pointer"
            >
              ✗ Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Exceptions Page
// ═══════════════════════════════════════════════════════════════════════════════
export default function Exceptions() {
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [filterType, setFilterType] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {};
      if (filterStatus) params.status = filterStatus;
      if (filterType) params.type = filterType;
      const data = await api.listExceptions(params);
      setExceptions(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterType]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAction(id: number, action: string) {
    try {
      await api.actOnException(id, action, `Manual ${action} from dashboard`);
      await load();
      if (selectedId === id) setSelectedId(null);
    } catch {
      // ignore
    }
  }

  async function handleBulkAction(action: string) {
    if (selectedIds.size === 0) return;
    try {
      await api.bulkAction(Array.from(selectedIds), action, `Bulk ${action} from dashboard`);
      setSelectedIds(new Set());
      await load();
    } catch {
      // ignore
    }
  }

  function toggleSelected(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const types = [...new Set(exceptions.map((e) => e.type))];
  const statusCounts = exceptions.reduce((acc, e) => {
    acc[e.status] = (acc[e.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Exceptions</h2>
          <p className="text-sm text-fintrix-text-muted mt-1.5">
            Review, investigate, and resolve reconciliation discrepancies
          </p>
        </div>
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-2 animate-fade-in">
            <span className="text-xs text-fintrix-text-muted mr-2">{selectedIds.size} selected</span>
            <button
              onClick={() => handleBulkAction("approve")}
              className="px-3 py-1.5 text-xs bg-fintrix-success/12 text-fintrix-success border border-fintrix-success/25 rounded-lg font-medium hover:bg-fintrix-success/20 cursor-pointer"
            >
              ✓ Approve All
            </button>
            <button
              onClick={() => handleBulkAction("escalate")}
              className="px-3 py-1.5 text-xs bg-fintrix-warning/12 text-fintrix-warning border border-fintrix-warning/25 rounded-lg font-medium hover:bg-fintrix-warning/20 cursor-pointer"
            >
              ⚑ Escalate All
            </button>
            <button
              onClick={() => setSelectedIds(new Set())}
              className="px-3 py-1.5 text-xs text-fintrix-text-muted hover:text-fintrix-text cursor-pointer"
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {/* Status Pills */}
      <div className="flex gap-2 flex-wrap">
        {["", "detected", "investigating", "resolved", "escalated"].map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
              filterStatus === s
                ? "bg-fintrix-primary/15 text-fintrix-primary border border-fintrix-primary/30"
                : "bg-fintrix-surface-2/50 text-fintrix-text-muted border border-fintrix-border-subtle hover:bg-fintrix-surface-2"
            }`}
          >
            {s || "All"} {s && statusCounts[s] ? `(${statusCounts[s]})` : s === "" ? `(${exceptions.length})` : ""}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="bg-fintrix-surface border border-fintrix-border rounded-lg px-3 py-2 text-sm text-fintrix-text focus:border-fintrix-primary outline-none cursor-pointer"
        >
          <option value="">All Types</option>
          {types.map((t) => (
            <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
          ))}
        </select>
        <button
          onClick={load}
          className="px-4 py-2 bg-fintrix-surface-2 border border-fintrix-border rounded-lg text-sm font-medium hover:bg-fintrix-surface-3 transition-colors cursor-pointer"
        >
          ↻ Refresh
        </button>
      </div>

      {/* Content */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Exception List */}
        <div className="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto pr-2">
          {loading ? (
            <div className="text-center py-16 text-fintrix-text-muted text-sm animate-pulse">
              Loading exceptions...
            </div>
          ) : exceptions.length === 0 ? (
            <div className="glass-card p-12 text-center">
              <div className="text-3xl mb-3 opacity-30">◈</div>
              <p className="text-sm text-fintrix-text-muted">No exceptions found. Run the pipeline first.</p>
            </div>
          ) : (
            exceptions.map((exc) => {
              const severityBorders: Record<string, string> = {
                low: "border-l-slate-500/50",
                medium: "border-l-amber-500/60",
                high: "border-l-orange-500/60",
                critical: "border-l-red-500/70",
              };

              return (
                <div
                  key={exc.id}
                  className={`flex items-start gap-3 p-4 rounded-xl border-l-[3px] transition-all duration-200 cursor-pointer ${
                    severityBorders[exc.severity] || "border-l-gray-500"
                  } ${
                    selectedId === exc.id
                      ? "bg-fintrix-primary/8 border border-fintrix-primary/30 shadow-lg shadow-fintrix-primary/5"
                      : "bg-fintrix-surface border border-fintrix-border hover:border-fintrix-primary/20 hover:bg-fintrix-surface-2/30"
                  }`}
                >
                  {/* Checkbox */}
                  <input
                    type="checkbox"
                    checked={selectedIds.has(exc.id)}
                    onChange={() => toggleSelected(exc.id)}
                    onClick={(e) => e.stopPropagation()}
                    className="mt-1 rounded border-fintrix-border accent-fintrix-primary cursor-pointer"
                  />

                  {/* Content */}
                  <button
                    className="flex-1 text-left cursor-pointer"
                    onClick={() => setSelectedId(selectedId === exc.id ? null : exc.id)}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-medium text-fintrix-text-muted">#{exc.id}</span>
                        <StatusBadge status={exc.status} />
                      </div>
                      <SeverityBadge severity={exc.severity} />
                    </div>
                    <p className="text-sm font-medium capitalize">
                      {exc.type.replace(/_/g, " ")}
                    </p>
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-xs text-fintrix-text-muted">
                        Risk: <span className="text-fintrix-warning font-semibold">{formatINR(exc.amount_at_risk)}</span>
                      </span>
                      {exc.investigation && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] text-fintrix-primary">🧠</span>
                          <span className="text-xs text-fintrix-primary font-mono">
                            {Math.round(exc.investigation.confidence * 100)}%
                          </span>
                        </div>
                      )}
                    </div>
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Detail / Deep Investigation Panel */}
        <div>
          {selectedId ? (
            <DeepInvestigationDrawer
              exceptionId={selectedId}
              onClose={() => setSelectedId(null)}
              onAction={handleAction}
            />
          ) : (
            <div className="glass-card p-16 text-center">
              <div className="text-4xl mb-4 opacity-20">🔍</div>
              <h3 className="text-sm font-semibold text-fintrix-text-muted mb-1">Select an Exception</h3>
              <p className="text-xs text-fintrix-text-dimmed">
                Click an exception to view deep investigation details
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
