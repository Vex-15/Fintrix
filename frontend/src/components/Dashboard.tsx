import { useState, useEffect, useRef, useCallback } from "react";
import {
  api,
  type PipelineResult,
  type DashboardStats,
} from "../api";

/** Format paise as ₹ amount */
function formatINR(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

function formatINRCompact(paise: number): string {
  const rupees = paise / 100;
  if (rupees >= 100000) return `₹${(rupees / 100000).toFixed(1)}L`;
  if (rupees >= 1000) return `₹${(rupees / 1000).toFixed(1)}K`;
  return `₹${rupees.toFixed(0)}`;
}

// ── Animated Counter ─────────────────────────────────────────────────────────
function AnimatedNumber({ value, duration = 800 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef<number>(0);

  useEffect(() => {
    const start = ref.current;
    const diff = value - start;
    const startTime = performance.now();

    function animate(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = Math.round(start + diff * eased);
      setDisplay(current);
      if (progress < 1) requestAnimationFrame(animate);
      else ref.current = value;
    }
    requestAnimationFrame(animate);
  }, [value, duration]);

  return <>{display}</>;
}

// ── Donut Chart ──────────────────────────────────────────────────────────────
function DonutChart({
  segments,
  size = 140,
  thickness = 12,
  centerLabel,
  centerValue,
}: {
  segments: { value: number; color: string; label: string }[];
  size?: number;
  thickness?: number;
  centerLabel?: string;
  centerValue?: string | number;
}) {
  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1;
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Background ring */}
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="rgba(30,48,80,0.3)"
          strokeWidth={thickness}
        />
        {segments.map((seg, i) => {
          const pct = seg.value / total;
          const dash = pct * circumference;
          const gap = circumference - dash;
          const currentOffset = offset;
          offset += dash;
          return (
            <circle
              key={i}
              cx={size / 2} cy={size / 2} r={radius}
              fill="none" stroke={seg.color}
              strokeWidth={thickness}
              strokeDasharray={`${dash} ${gap}`}
              strokeDashoffset={-currentOffset}
              strokeLinecap="round"
              className="transition-all duration-1000 ease-out"
              style={{ filter: `drop-shadow(0 0 4px ${seg.color}40)` }}
            />
          );
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {centerValue !== undefined && (
          <span className="text-2xl font-bold text-fintrix-text">{centerValue}</span>
        )}
        {centerLabel && (
          <span className="text-[10px] text-fintrix-text-muted uppercase tracking-wider">{centerLabel}</span>
        )}
      </div>
    </div>
  );
}

// ── Metric Card (Glassmorphic) ───────────────────────────────────────────────
function MetricCard({
  label,
  value,
  sub,
  icon,
  color = "text-fintrix-text",
  glowClass = "",
  delay = 0,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  icon?: string;
  color?: string;
  glowClass?: string;
  delay?: number;
}) {
  return (
    <div
      className={`glass-card glass-card-hover p-5 ${glowClass}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start justify-between mb-3">
        <p className="text-[11px] text-fintrix-text-muted uppercase tracking-wider font-medium">{label}</p>
        {icon && <span className="material-symbols-outlined opacity-30" style={{ fontSize: "20px" }}>{icon}</span>}
      </div>
      <p className={`text-2xl font-bold tracking-tight ${color}`}>{value}</p>
      {sub && <p className="text-[11px] text-fintrix-text-muted mt-1.5">{sub}</p>}
    </div>
  );
}

// ── Pipeline Stage ───────────────────────────────────────────────────────────
function PipelineStage({
  label,
  icon,
  status,
  detail,
}: {
  label: string;
  icon: string;
  status: "idle" | "running" | "done";
  detail?: string;
}) {
  const styles = {
    idle: "border-fintrix-border bg-fintrix-surface-2/50 text-fintrix-text-muted",
    running: "border-fintrix-primary/50 bg-fintrix-primary/8 text-fintrix-primary animate-glow-pulse",
    done: "border-fintrix-success/40 bg-fintrix-success/8 text-fintrix-success",
  };

  return (
    <div className={`flex-1 rounded-xl border p-4 transition-all duration-500 ${styles[status]}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>{icon}</span>
        <span className="text-sm font-semibold">{label}</span>
        {status === "done" && <span className="material-symbols-outlined ml-auto icon-sm">check_circle</span>}
        {status === "running" && <span className="ml-auto text-xs animate-pulse">●</span>}
      </div>
      {detail && <p className="text-[11px] opacity-70 mt-1">{detail}</p>}
    </div>
  );
}


// ── Recent Exception Row ─────────────────────────────────────────────────────
function RecentExceptionRow({ exc }: { exc: DashboardStats["recent_exceptions"][0] }) {
  const severityColors: Record<string, string> = {
    low: "border-l-gray-500",
    medium: "border-l-amber-500",
    high: "border-l-orange-500",
    critical: "border-l-red-500",
  };

  const statusIcons: Record<string, string> = {
    detected: "◌",
    investigating: "⟳",
    resolved: "✓",
    escalated: "⚑",
  };

  return (
    <div className={`flex items-center gap-4 py-3 px-4 border-l-2 ${severityColors[exc.severity] || "border-l-gray-500"} hover:bg-fintrix-surface-2/30 transition-colors rounded-r-lg`}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-fintrix-text-muted">#{exc.id}</span>
          <span className="text-xs capitalize text-fintrix-text">
            {exc.type.replace(/_/g, " ")}
          </span>
        </div>
        {exc.investigation && (
          <p className="text-[11px] text-fintrix-text-muted mt-0.5 truncate">
            {exc.investigation.root_cause}
          </p>
        )}
      </div>
      <div className="text-right shrink-0">
        <p className="text-xs font-medium text-fintrix-warning">{formatINRCompact(exc.amount_at_risk)}</p>
        <p className="text-[10px] text-fintrix-text-muted mt-0.5">
          {statusIcons[exc.status]} {exc.status}
        </p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main Dashboard
// ═══════════════════════════════════════════════════════════════════════════════
export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [pipelineStage, setPipelineStage] = useState<"idle" | "generating" | "reconciling" | "investigating" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [sseEvents, setSseEvents] = useState<string[]>([]);

  // Load dashboard stats
  const loadStats = useCallback(async () => {
    try {
      const s = await api.getDashboardStats();
      setStats(s);
    } catch {
      // May fail if no data yet
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  // SSE listener for live events
  useEffect(() => {
    const es = new EventSource("/api/events/stream");

    es.addEventListener("pipeline.step", (e) => {
      const data = JSON.parse(e.data);
      setSseEvents((prev) => [...prev.slice(-30), `${data.step}: ${data.status}`]);
    });
    es.addEventListener("pipeline.completed", (e) => {
      const data = JSON.parse(e.data);
      setSseEvents((prev) => [
        ...prev.slice(-30),
        `✓ Pipeline complete — ${data.matched} matched, ${data.auto_resolved} auto-resolved`,
      ]);
    });
    es.addEventListener("investigation.completed", (e) => {
      const data = JSON.parse(e.data);
      setSseEvents((prev) => [
        ...prev.slice(-30),
        `🧠 Exception #${data.exception_id} investigated (${Math.round(data.confidence * 100)}% confidence)`,
      ]);
    });

    return () => es.close();
  }, []);

  // Generate data + run pipeline
  async function handleFullDemo() {
    setLoading(true);
    setError(null);
    setPipelineResult(null);
    setSseEvents([]);

    try {
      // Step 1: Generate data
      setPipelineStage("generating");
      await api.generateData();
      await loadStats();

      // Step 2: Run full pipeline
      setPipelineStage("reconciling");
      const result = await api.runFullPipeline();
      setPipelineResult(result);
      setPipelineStage("done");

      // Refresh stats
      await loadStats();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pipeline failed");
      setPipelineStage("idle");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunPipeline() {
    setLoading(true);
    setError(null);
    setPipelineResult(null);
    setSseEvents([]);

    try {
      setPipelineStage("reconciling");
      const result = await api.runFullPipeline();
      setPipelineResult(result);
      setPipelineStage("done");
      await loadStats();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pipeline failed");
      setPipelineStage("idle");
    } finally {
      setLoading(false);
    }
  }

  const hasData = stats && stats.data_sources.transactions > 0;

  return (
    <div className="space-y-8 stagger-children">
      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Reconciliation Dashboard</h2>
          <p className="text-sm text-fintrix-text-muted mt-1.5">
            Deterministic reconciliation → AI investigation → evidence-backed resolution
          </p>
        </div>
        <div className="flex gap-3">
          {!hasData ? (
            <button
              onClick={handleFullDemo}
              disabled={loading}
              className="btn-gradient disabled:opacity-40"
              id="btn-full-demo"
            >
              <span>{loading ? "Running..." : "⚡ Load Data & Run Pipeline"}</span>
            </button>
          ) : (
            <button
              onClick={handleRunPipeline}
              disabled={loading}
              className="btn-gradient disabled:opacity-40"
              id="btn-run-pipeline"
            >
              <span>{loading ? "Running Pipeline..." : "▶ Run Full Pipeline"}</span>
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="glass-card p-4 border-fintrix-danger/30 bg-fintrix-danger/5">
          <p className="text-sm text-fintrix-danger">{error}</p>
        </div>
      )}

      {/* ── Pipeline Visualizer ────────────────────────────────────── */}
      {(loading || pipelineResult) && (
        <div className="glass-card p-6">
          <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-4">
            Pipeline Execution
          </h3>
          <div className="flex items-center gap-2">
            <PipelineStage
              label="Ingest"
              icon="download"
              status={pipelineStage === "generating" ? "running" : pipelineStage !== "idle" ? "done" : "idle"}
              detail={stats ? `${stats.data_sources.transactions} txns` : undefined}
            />
            <div className={`pipeline-connector ${pipelineStage !== "idle" && pipelineStage !== "generating" ? "pipeline-connector-active" : ""}`} />
            <PipelineStage
              label="Reconcile"
              icon="balance"
              status={pipelineStage === "reconciling" ? "running" : pipelineResult ? "done" : "idle"}
              detail={pipelineResult ? `${pipelineResult.reconciliation.matched} matched` : undefined}
            />
            <div className={`pipeline-connector ${pipelineStage === "investigating" || pipelineStage === "done" ? "pipeline-connector-active" : ""}`} />
            <PipelineStage
              label="Investigate"
              icon="psychology"
              status={pipelineStage === "investigating" ? "running" : pipelineResult ? "done" : "idle"}
              detail={pipelineResult ? `${pipelineResult.investigation.total_investigated} analyzed` : undefined}
            />
            <div className={`pipeline-connector ${pipelineStage === "done" ? "pipeline-connector-active" : ""}`} />
            <PipelineStage
              label="Resolve"
              icon="task_alt"
              status={pipelineStage === "done" ? "done" : "idle"}
              detail={pipelineResult ? `${pipelineResult.investigation.auto_resolved} auto-resolved` : undefined}
            />
          </div>
        </div>
      )}

      {/* ── Key Metrics ───────────────────────────────────────────── */}
      {pipelineResult ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
          <MetricCard
            label="Match Rate"
            value={`${((pipelineResult.reconciliation.matched / Math.max(pipelineResult.reconciliation.total_records, 1)) * 100).toFixed(1)}%`}
            sub={`${pipelineResult.reconciliation.matched} of ${pipelineResult.reconciliation.total_records}`}
            icon="verified"
            color="text-fintrix-success"
            glowClass="glow-success"
          />
          <MetricCard
            label="Exceptions Found"
            value={pipelineResult.reconciliation.exceptions}
            sub="Discrepancies detected"
            icon="warning"
            color="text-fintrix-warning"
            glowClass="glow-warning"
          />
          <MetricCard
            label="Auto-Resolved"
            value={pipelineResult.investigation.auto_resolved}
            sub="High confidence · low risk"
            icon="auto_fix_high"
            color="text-fintrix-accent"
            glowClass="glow-blue"
          />
          <MetricCard
            label="Needs Review"
            value={pipelineResult.investigation.escalated}
            sub="Human approval required"
            icon="flag"
            color="text-fintrix-danger"
            glowClass="glow-danger"
          />
        </div>
      ) : stats && hasData ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
          <MetricCard
            label="Transactions"
            value={<AnimatedNumber value={stats.data_sources.transactions} />}
            sub="Payments · Refunds · Adjustments"
            icon="receipt_long"
          />
          <MetricCard
            label="Settlements"
            value={<AnimatedNumber value={stats.data_sources.settlements} />}
            sub="Batched payouts"
            icon="payments"
          />
          <MetricCard
            label="Bank Entries"
            value={<AnimatedNumber value={stats.data_sources.bank_statements} />}
            sub="Bank credit records"
            icon="account_balance"
          />
          <MetricCard
            label="Exceptions"
            value={<AnimatedNumber value={stats.exceptions.total} />}
            sub={`${stats.exceptions.pending} pending · ${stats.exceptions.resolved} resolved`}
            icon="error_outline"
            color={stats.exceptions.pending > 0 ? "text-fintrix-warning" : "text-fintrix-success"}
          />
        </div>
      ) : (
        <div className="glass-card p-12 text-center">
          <span className="material-symbols-outlined text-fintrix-text-dimmed mb-4 block" style={{ fontSize: "48px", opacity: 0.25 }}>database</span>
          <h3 className="text-lg font-semibold text-fintrix-text-muted mb-2">No data loaded yet</h3>
          <p className="text-sm text-fintrix-text-dimmed mb-6">
            Click "Load Data & Run Pipeline" to generate synthetic financial records and run the full reconciliation.
          </p>
        </div>
      )}

      {/* ── Charts + Recent Activity ──────────────────────────────── */}
      {pipelineResult && stats && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Donut: Match breakdown */}
          <div className="glass-card p-6">
            <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-5">
              Reconciliation Breakdown
            </h3>
            <div className="flex items-center justify-center">
              <DonutChart
                segments={[
                  { value: pipelineResult.reconciliation.matched, color: "#10b981", label: "Matched" },
                  { value: pipelineResult.reconciliation.mismatched, color: "#f59e0b", label: "Mismatched" },
                  { value: pipelineResult.reconciliation.unmatched, color: "#ef4444", label: "Unmatched" },
                ]}
                centerValue={`${((pipelineResult.reconciliation.matched / Math.max(pipelineResult.reconciliation.total_records, 1)) * 100).toFixed(0)}%`}
                centerLabel="Match Rate"
              />
            </div>
            <div className="mt-5 space-y-2">
              {[
                { label: "Matched", value: pipelineResult.reconciliation.matched, color: "bg-emerald-500" },
                { label: "Mismatched", value: pipelineResult.reconciliation.mismatched, color: "bg-amber-500" },
                { label: "Unmatched", value: pipelineResult.reconciliation.unmatched, color: "bg-red-500" },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <div className={`w-2.5 h-2.5 rounded-full ${item.color}`} />
                    <span className="text-fintrix-text-muted">{item.label}</span>
                  </div>
                  <span className="font-mono font-medium">{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Donut: Resolution breakdown */}
          <div className="glass-card p-6">
            <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-5">
              Resolution Status
            </h3>
            <div className="flex items-center justify-center">
              <DonutChart
                segments={[
                  { value: pipelineResult.investigation.auto_resolved, color: "#06b6d4", label: "Auto-resolved" },
                  { value: pipelineResult.investigation.escalated, color: "#ef4444", label: "Escalated" },
                  { value: pipelineResult.investigation.human_review || 0, color: "#f59e0b", label: "Human Review" },
                ]}
                centerValue={pipelineResult.investigation.total_investigated}
                centerLabel="Investigated"
              />
            </div>
            <div className="mt-5 space-y-2">
              {[
                { label: "Auto-resolved", value: pipelineResult.investigation.auto_resolved, color: "bg-cyan-500" },
                { label: "Escalated", value: pipelineResult.investigation.escalated, color: "bg-red-500" },
                { label: "Human Review", value: pipelineResult.investigation.human_review || 0, color: "bg-amber-500" },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <div className={`w-2.5 h-2.5 rounded-full ${item.color}`} />
                    <span className="text-fintrix-text-muted">{item.label}</span>
                  </div>
                  <span className="font-mono font-medium">{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Exception types */}
          <div className="glass-card p-6">
            <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-5">
              Exception Types
            </h3>
            {stats.exceptions.by_type && Object.keys(stats.exceptions.by_type).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(stats.exceptions.by_type)
                  .sort((a, b) => b[1] - a[1])
                  .map(([type, count]) => {
                    const total = stats.exceptions.total || 1;
                    const pct = Math.round((count / total) * 100);
                    return (
                      <div key={type}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-fintrix-text-muted capitalize">{type.replace(/_/g, " ")}</span>
                          <span className="font-mono">{count} ({pct}%)</span>
                        </div>
                        <div className="h-1.5 bg-fintrix-surface-2 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-fintrix-primary to-fintrix-accent rounded-full transition-all duration-1000"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
              </div>
            ) : (
              <p className="text-sm text-fintrix-text-muted">No exceptions detected</p>
            )}
          </div>
        </div>
      )}

      {/* ── Performance + Recent ──────────────────────────────────── */}
      {pipelineResult && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Performance metrics */}
          <div className="glass-card p-6">
            <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-4">
              Performance Metrics
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-[11px] text-fintrix-text-muted mb-1">Throughput</p>
                <p className="text-xl font-bold text-fintrix-text">
                  {Math.round(pipelineResult.reconciliation.total_records / (pipelineResult.reconciliation.duration_ms / 1000))}
                  <span className="text-xs text-fintrix-text-muted ml-1">rec/s</span>
                </p>
              </div>
              <div>
                <p className="text-[11px] text-fintrix-text-muted mb-1">Pipeline Duration</p>
                <p className="text-xl font-bold text-fintrix-text">
                  {pipelineResult.reconciliation.duration_ms}
                  <span className="text-xs text-fintrix-text-muted ml-1">ms</span>
                </p>
              </div>
              <div>
                <p className="text-[11px] text-fintrix-text-muted mb-1">AI Investigated</p>
                <p className="text-xl font-bold text-fintrix-text">
                  {pipelineResult.investigation.total_investigated}
                  <span className="text-xs text-fintrix-text-muted ml-1">exceptions</span>
                </p>
              </div>
              <div>
                <p className="text-[11px] text-fintrix-text-muted mb-1">Audit Coverage</p>
                <p className="text-xl font-bold text-fintrix-success">
                  100<span className="text-xs">%</span>
                </p>
              </div>
            </div>
          </div>

          {/* Live event feed */}
          <div className="glass-card p-6">
            <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-4">
              Live Activity Feed
            </h3>
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {sseEvents.length > 0 ? (
                sseEvents.map((evt, i) => (
                  <div
                    key={i}
                    className="text-[12px] font-mono text-fintrix-text-muted py-1 animate-fade-in"
                  >
                    <span className="text-fintrix-accent mr-2">›</span>
                    {evt}
                  </div>
                ))
              ) : (
                <p className="text-sm text-fintrix-text-dimmed">Waiting for pipeline events...</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Recent Exceptions ─────────────────────────────────────── */}
      {stats && stats.recent_exceptions.length > 0 && (
        <div className="glass-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider">
              Recent Exceptions
            </h3>
            <span className="text-[11px] text-fintrix-text-dimmed">Last 5</span>
          </div>
          <div className="space-y-1">
            {stats.recent_exceptions.map((exc) => (
              <RecentExceptionRow key={exc.id} exc={exc} />
            ))}
          </div>
        </div>
      )}

      {/* ── Financial Summary ─────────────────────────────────────── */}
      {stats && stats.financial.total_at_risk > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <MetricCard
            label="Total Amount at Risk"
            value={formatINR(stats.financial.total_at_risk)}
            sub="Across all unresolved exceptions"
            icon="warning"
            color="text-fintrix-warning"
            glowClass="glow-warning"
          />
          <MetricCard
            label="Amount Resolved"
            value={formatINR(stats.financial.resolved_at_risk)}
            sub="Successfully reconciled"
            icon="check_circle"
            color="text-fintrix-success"
            glowClass="glow-success"
          />
          <MetricCard
            label="Pending Review"
            value={formatINR(stats.financial.pending_at_risk)}
            sub="Awaiting human decision"
            icon="hourglass_top"
            color="text-fintrix-danger"
          />
        </div>
      )}
    </div>
  );
}
