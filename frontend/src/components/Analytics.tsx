import { useState, useEffect } from "react";
import { api, type TrendData, type SLAData, type ROIData } from "../api";

export default function Analytics() {
  const [trends, setTrends] = useState<TrendData | null>(null);
  const [sla, setSLA] = useState<SLAData | null>(null);
  const [roi, setROI] = useState<ROIData | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(30);

  useEffect(() => {
    loadData();
  }, [period]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [t, s, r] = await Promise.all([
        api.getTrends(period),
        api.getSLA(period),
        api.getROI(),
      ]);
      setTrends(t);
      setSLA(s);
      setROI(r);
    } catch (err) {
      console.error("Failed to load analytics:", err);
    } finally {
      setLoading(false);
    }
  };

  const fmt = (n: number) => n.toLocaleString("en-IN");
  const fmtR = (paise: number) => `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
  const fmtPct = (n: number) => `${(n * 100).toFixed(1)}%`;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-fintrix-primary/30 border-t-fintrix-primary rounded-full animate-spin mx-auto mb-3" />
          <p className="text-fintrix-text-muted text-sm">Loading analytics...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold gradient-text">Analytics</h2>
          <p className="text-fintrix-text-muted text-sm mt-1">Trends, SLA tracking & ROI analysis</p>
        </div>
        <div className="flex gap-2">
          {[7, 14, 30, 60].map((d) => (
            <button
              key={d}
              onClick={() => setPeriod(d)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                period === d
                  ? "bg-fintrix-primary/15 text-fintrix-primary"
                  : "text-fintrix-text-muted hover:bg-fintrix-surface-2"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* ROI Summary Cards */}
      {roi && (
        <div className="grid grid-cols-4 gap-4">
          <div className="glass-card rounded-xl p-5 border border-fintrix-border-subtle">
            <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">Auto-Resolve Rate</p>
            <p className="text-3xl font-bold text-emerald-400">{roi.auto_resolve_rate}%</p>
            <p className="text-xs text-fintrix-text-dimmed mt-1">{fmt(roi.auto_resolved)} of {fmt(roi.total_exceptions)}</p>
          </div>
          <div className="glass-card rounded-xl p-5 border border-fintrix-border-subtle">
            <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">Hours Saved</p>
            <p className="text-3xl font-bold text-blue-400">{fmt(roi.time_savings.total_hours_saved)}</p>
            <p className="text-xs text-fintrix-text-dimmed mt-1">{fmt(roi.time_savings.reconciliation_hours)}h recon + {fmt(roi.time_savings.investigation_hours)}h investigation</p>
          </div>
          <div className="glass-card rounded-xl p-5 border border-fintrix-border-subtle">
            <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">Cost Saved</p>
            <p className="text-3xl font-bold text-amber-400">₹{fmt(roi.cost_savings.total_saved_rupees)}</p>
            <p className="text-xs text-fintrix-text-dimmed mt-1">@ ₹{roi.cost_savings.hourly_rate}/hr</p>
          </div>
          <div className="glass-card rounded-xl p-5 border border-fintrix-border-subtle">
            <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">AI Speedup</p>
            <p className="text-3xl font-bold text-violet-400">{roi.accuracy.speedup_factor ?? "—"}x</p>
            <p className="text-xs text-fintrix-text-dimmed mt-1">vs {roi.accuracy.manual_time_per_exception_min}min manual</p>
          </div>
        </div>
      )}

      {/* SLA Metrics */}
      {sla && (
        <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
          <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
            <span className="text-amber-400">⏱</span> SLA Performance
          </h3>
          <div className="grid grid-cols-3 gap-6">
            <div>
              <p className="text-sm text-fintrix-text-muted mb-3 font-medium">AI Investigation Latency</p>
              <div className="space-y-2">
                {[
                  { label: "P50", value: sla.investigation_latency_ms.p50, color: "text-emerald-400" },
                  { label: "P95", value: sla.investigation_latency_ms.p95, color: "text-amber-400" },
                  { label: "P99", value: sla.investigation_latency_ms.p99, color: "text-red-400" },
                ].map((m) => (
                  <div key={m.label} className="flex items-center justify-between">
                    <span className="text-xs text-fintrix-text-dimmed">{m.label}</span>
                    <span className={`text-sm font-mono font-medium ${m.color}`}>
                      {m.value != null ? `${fmt(m.value)}ms` : "—"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="text-sm text-fintrix-text-muted mb-3 font-medium">Time to Resolve</p>
              <div className="space-y-2">
                {[
                  { label: "P50", value: sla.time_to_resolve_seconds.p50, color: "text-emerald-400" },
                  { label: "P95", value: sla.time_to_resolve_seconds.p95, color: "text-amber-400" },
                  { label: "P99", value: sla.time_to_resolve_seconds.p99, color: "text-red-400" },
                ].map((m) => (
                  <div key={m.label} className="flex items-center justify-between">
                    <span className="text-xs text-fintrix-text-dimmed">{m.label}</span>
                    <span className={`text-sm font-mono font-medium ${m.color}`}>
                      {m.value != null ? `${m.value < 60 ? `${m.value}s` : `${(m.value / 60).toFixed(1)}m`}` : "—"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="text-sm text-fintrix-text-muted mb-3 font-medium">Reconciliation Duration</p>
              <div className="space-y-2">
                {[
                  { label: "P50", value: sla.reconciliation_duration_ms.p50, color: "text-emerald-400" },
                  { label: "P95", value: sla.reconciliation_duration_ms.p95, color: "text-amber-400" },
                  { label: "P99", value: sla.reconciliation_duration_ms.p99, color: "text-red-400" },
                ].map((m) => (
                  <div key={m.label} className="flex items-center justify-between">
                    <span className="text-xs text-fintrix-text-dimmed">{m.label}</span>
                    <span className={`text-sm font-mono font-medium ${m.color}`}>
                      {m.value != null ? `${fmt(m.value)}ms` : "—"}
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-3 pt-3 border-t border-fintrix-border-subtle">
                <div className="flex justify-between text-xs">
                  <span className="text-fintrix-text-dimmed">Throughput</span>
                  <span className="text-fintrix-text-muted font-mono">{fmt(sla.throughput.total_records_processed)} records</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Trend Data */}
      {trends && (
        <div className="grid grid-cols-2 gap-6">
          {/* Accuracy Trend */}
          <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
            <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
              <span className="text-emerald-400">📈</span> Accuracy Trend
            </h3>
            {trends.run_trends.length > 0 ? (
              <div className="space-y-2">
                {trends.run_trends.slice(-10).map((r) => (
                  <div key={r.run_id} className="flex items-center gap-3">
                    <span className="text-[10px] text-fintrix-text-dimmed font-mono w-20 shrink-0">
                      {r.date?.split("T")[0] ?? "—"}
                    </span>
                    <div className="flex-1 h-4 bg-fintrix-surface-2/50 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-500"
                        style={{ width: `${r.accuracy * 100}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono text-emerald-400 w-12 text-right">
                      {fmtPct(r.accuracy)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-fintrix-text-dimmed">No runs yet. Run the pipeline to see trends.</p>
            )}
            <div className="mt-4 pt-4 border-t border-fintrix-border-subtle">
              <div className="flex justify-between text-xs">
                <span className="text-fintrix-text-dimmed">Average Accuracy</span>
                <span className="text-emerald-400 font-medium">{fmtPct(trends.summary.avg_accuracy)}</span>
              </div>
            </div>
          </div>

          {/* Exception Volume */}
          <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
            <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
              <span className="text-red-400">📊</span> Exception Volume
            </h3>
            {trends.exception_trends.length > 0 ? (
              <div className="space-y-2">
                {trends.exception_trends.slice(-10).map((e) => {
                  const maxTotal = Math.max(...trends.exception_trends.map((t) => t.total), 1);
                  return (
                    <div key={e.date} className="flex items-center gap-3">
                      <span className="text-[10px] text-fintrix-text-dimmed font-mono w-20 shrink-0">
                        {e.date}
                      </span>
                      <div className="flex-1 h-4 bg-fintrix-surface-2/50 rounded-full overflow-hidden flex">
                        <div
                          className="h-full bg-emerald-500/80 transition-all"
                          style={{ width: `${(e.resolved / maxTotal) * 100}%` }}
                        />
                        <div
                          className="h-full bg-amber-500/80 transition-all"
                          style={{ width: `${(e.escalated / maxTotal) * 100}%` }}
                        />
                        <div
                          className="h-full bg-red-500/80 transition-all"
                          style={{ width: `${((e.total - e.resolved - e.escalated) / maxTotal) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-fintrix-text-muted w-8 text-right">{e.total}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-fintrix-text-dimmed">No exception data yet.</p>
            )}
            <div className="mt-4 pt-4 border-t border-fintrix-border-subtle flex gap-4 text-[10px]">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Resolved</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500" /> Escalated</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" /> Pending</span>
            </div>
          </div>
        </div>
      )}

      {/* ROI Detailed Card */}
      {roi && (
        <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
          <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
            <span className="text-emerald-400">💰</span> ROI Calculator
          </h3>
          <div className="grid grid-cols-3 gap-8">
            <div className="space-y-3">
              <h4 className="text-xs text-fintrix-text-muted uppercase tracking-wider font-medium">Processing Volume</h4>
              <div className="flex justify-between"><span className="text-sm text-fintrix-text-dimmed">Records Processed</span><span className="text-sm font-mono text-fintrix-text">{fmt(roi.total_records_processed)}</span></div>
              <div className="flex justify-between"><span className="text-sm text-fintrix-text-dimmed">Exceptions Detected</span><span className="text-sm font-mono text-fintrix-text">{fmt(roi.total_exceptions)}</span></div>
              <div className="flex justify-between"><span className="text-sm text-fintrix-text-dimmed">Auto-Resolved</span><span className="text-sm font-mono text-emerald-400">{fmt(roi.auto_resolved)}</span></div>
            </div>
            <div className="space-y-3">
              <h4 className="text-xs text-fintrix-text-muted uppercase tracking-wider font-medium">Time Savings</h4>
              <div className="flex justify-between"><span className="text-sm text-fintrix-text-dimmed">Reconciliation</span><span className="text-sm font-mono text-fintrix-text">{roi.time_savings.reconciliation_hours}h</span></div>
              <div className="flex justify-between"><span className="text-sm text-fintrix-text-dimmed">Investigation</span><span className="text-sm font-mono text-fintrix-text">{roi.time_savings.investigation_hours}h</span></div>
              <div className="flex justify-between border-t border-fintrix-border-subtle pt-2"><span className="text-sm text-fintrix-text-muted font-medium">Total Saved</span><span className="text-sm font-mono text-blue-400 font-bold">{roi.time_savings.total_hours_saved}h</span></div>
            </div>
            <div className="space-y-3">
              <h4 className="text-xs text-fintrix-text-muted uppercase tracking-wider font-medium">Financial Impact</h4>
              <div className="flex justify-between"><span className="text-sm text-fintrix-text-dimmed">Cost Saved</span><span className="text-sm font-mono text-emerald-400">₹{fmt(roi.cost_savings.total_saved_rupees)}</span></div>
              <div className="flex justify-between"><span className="text-sm text-fintrix-text-dimmed">Risk Resolved</span><span className="text-sm font-mono text-fintrix-text">₹{fmt(roi.amount_at_risk_resolved_rupees)}</span></div>
              <div className="flex justify-between"><span className="text-sm text-fintrix-text-dimmed">AI Latency</span><span className="text-sm font-mono text-violet-400">{roi.accuracy.avg_ai_latency_ms ?? "—"}ms</span></div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
