import { useState, useEffect } from "react";
import { api, type TrendData, type SLAData, type ROIData } from "../api";

export default function Analytics() {
  const [trends, setTrends] = useState<TrendData | null>(null);
  const [sla, setSLA] = useState<SLAData | null>(null);
  const [roi, setROI] = useState<ROIData | null>(null);
  
  // New Analytics State
  const [forecast, setForecast] = useState<any>(null);
  const [tax, setTax] = useState<any>(null);
  const [calibration, setCalibration] = useState<any>(null);
  const [sensitivity, setSensitivity] = useState<any>(null);
  const [sliderThreshold, setSliderThreshold] = useState<number>(0.85);

  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(30);

  useEffect(() => {
    loadData();
  }, [period]);

  const loadData = async () => {
    setLoading(true);
    try {
      const results = await Promise.allSettled([
        api.getTrends(period),
        api.getSLA(period),
        api.getROI(),
        api.getForecast(14).catch(() => null),
        api.getTaxReconciliation().catch(() => null),
        api.getConfidenceCalibration().catch(() => null),
        api.getThresholdSensitivity().catch(() => null),
      ]);
      const val = (r: PromiseSettledResult<any>) => r.status === "fulfilled" ? r.value : null;
      setTrends(val(results[0]));
      setSLA(val(results[1]));
      setROI(val(results[2]));
      setForecast(val(results[3]));
      setTax(val(results[4]));
      setCalibration(val(results[5]));
      setSensitivity(val(results[6]));
      const sens = val(results[6]);
      if (sens && sens.current_threshold) {
        setSliderThreshold(sens.current_threshold);
      }
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

      {/* Cash Forecast */}
      {forecast && (
        <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
          <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
            <span className="text-blue-400">📈</span> Cash Flow Forecast (Next {forecast.forecast_days} Days)
          </h3>
          <div className="grid grid-cols-3 gap-6 mb-6">
            <div>
              <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">Projected Inflow</p>
              <p className="text-2xl font-bold text-blue-400">₹{fmt(forecast.total_projected_inflow_rupees)}</p>
            </div>
            <div>
              <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">Pending Settlements</p>
              <p className="text-2xl font-bold text-fintrix-text">₹{fmt(forecast.pending_captured_unsettled_rupees)}</p>
            </div>
            <div>
              <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">Trend</p>
              <p className={`text-2xl font-bold ${forecast.trend === 'up' ? 'text-emerald-400' : 'text-amber-400'}`}>
                {forecast.trend === 'up' ? '↑' : '↓'} {forecast.trend}
              </p>
            </div>
          </div>
          
          <div className="h-40 flex items-end gap-2 border-b border-fintrix-border-subtle pb-2">
            {forecast.daily_forecasts.map((d: any) => {
              const maxAmt = Math.max(...forecast.daily_forecasts.map((df: any) => df.projected_rupees));
              const heightPct = Math.max((d.projected_rupees / maxAmt) * 100, 5);
              return (
                <div key={d.date} className="flex-1 flex flex-col items-center gap-2 group relative">
                  <div 
                    className="w-full bg-blue-500/80 rounded-t-sm hover:bg-blue-400 transition-colors"
                    style={{ height: `${heightPct}%` }}
                  />
                  <div className="text-[9px] text-fintrix-text-dimmed -rotate-45 origin-top-left absolute -bottom-8">
                    {d.date.split('-').slice(1).join('/')}
                  </div>
                  {/* Tooltip */}
                  <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-black/80 px-2 py-1 rounded text-xs opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10 pointer-events-none">
                    ₹{fmt(d.projected_rupees)}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="h-8"></div>
        </div>
      )}

      {/* Tax Reconciliation */}
      {tax && (
        <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
          <div className="flex justify-between items-start mb-4">
            <h3 className="text-lg font-semibold text-fintrix-text flex items-center gap-2">
              <span className="text-amber-400">⚖️</span> Tax & Fee Reconciliation
            </h3>
            <div className="text-right">
              <p className="text-xs text-fintrix-text-muted uppercase tracking-wider">Total Discrepancy</p>
              <p className="text-xl font-bold text-amber-400">
                ₹{fmt(tax.summary.total_fee_difference_rupees + tax.summary.total_gst_difference_rupees)}
              </p>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-6">
            <div>
              <h4 className="text-sm font-medium text-fintrix-text-muted mb-3">Match Breakdown</h4>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-fintrix-text flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" /> Exact Match
                  </span>
                  <span className="text-sm font-mono text-fintrix-text">{tax.summary.exact_matches}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-fintrix-text flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-blue-400" /> Rounding Diff
                  </span>
                  <span className="text-sm font-mono text-fintrix-text">{tax.summary.rounding_differences}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-fintrix-text flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-amber-400" /> Rate Change
                  </span>
                  <span className="text-sm font-mono text-fintrix-text">{tax.summary.rate_changes}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-fintrix-text flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-red-400" /> Unexplained
                  </span>
                  <span className="text-sm font-mono text-fintrix-text">{tax.summary.unexplained}</span>
                </div>
              </div>
            </div>
            
            <div>
              <h4 className="text-sm font-medium text-fintrix-text-muted mb-3">Discrepancy Details</h4>
              <div className="space-y-3 p-4 bg-fintrix-surface-2/50 rounded-lg border border-fintrix-border/50">
                <div className="flex justify-between">
                  <span className="text-xs text-fintrix-text-dimmed">Total Transactions</span>
                  <span className="text-xs font-mono">{tax.summary.total_transactions}</span>
                </div>
                <div className="flex justify-between border-t border-fintrix-border-subtle pt-2">
                  <span className="text-xs text-fintrix-text-dimmed">Fee Discrepancy</span>
                  <span className="text-xs font-mono text-amber-400">₹{fmt(tax.summary.total_fee_difference_rupees)}</span>
                </div>
                <div className="flex justify-between border-t border-fintrix-border-subtle pt-2">
                  <span className="text-xs text-fintrix-text-dimmed">GST Discrepancy</span>
                  <span className="text-xs font-mono text-red-400">₹{fmt(tax.summary.total_gst_difference_rupees)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* AI Performance & Sensitivity Grid */}
      <div className="grid grid-cols-2 gap-6">
        
        {/* Confidence Calibration */}
        {calibration && (
          <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
            <div className="flex justify-between items-start mb-6">
              <h3 className="text-lg font-semibold text-fintrix-text flex items-center gap-2">
                <span className="text-violet-400">🎯</span> Confidence Calibration
              </h3>
              <div className="text-right">
                <p className="text-xs text-fintrix-text-muted uppercase tracking-wider">ECE Score</p>
                <p className={`text-xl font-bold ${
                  calibration.ece_interpretation === 'excellent' ? 'text-emerald-400' :
                  calibration.ece_interpretation === 'good' ? 'text-blue-400' :
                  calibration.ece_interpretation === 'fair' ? 'text-amber-400' : 'text-red-400'
                }`}>
                  {calibration.ece.toFixed(4)}
                </p>
              </div>
            </div>

            <div className="h-48 flex items-end gap-3 border-b border-l border-fintrix-border-subtle pl-2 pb-2 relative">
              <div className="absolute left-0 bottom-0 top-0 -ml-8 flex flex-col justify-between text-[10px] text-fintrix-text-dimmed py-2">
                <span>100%</span>
                <span>50%</span>
                <span>0%</span>
              </div>
              
              {calibration.calibration_curve.map((band: any, i: number) => {
                if (band.count === 0) return <div key={i} className="flex-1" />;
                const predictedPct = band.predicted_confidence * 100;
                const actualPct = band.actual_accuracy * 100;
                
                return (
                  <div key={band.confidence_range} className="flex-1 flex justify-center items-end relative group h-full">
                    {/* Perfect Calibration Line */}
                    <div className="absolute w-full border-t border-dashed border-white/20 z-0" style={{ bottom: `${predictedPct}%` }} />
                    
                    {/* Actual Accuracy Bar */}
                    <div 
                      className="w-4/5 bg-violet-500/80 rounded-t-sm z-10 transition-all hover:bg-violet-400"
                      style={{ height: `${actualPct}%` }}
                    />
                    
                    {/* Tooltip */}
                    <div className="absolute -top-10 bg-black/90 p-2 rounded text-xs opacity-0 group-hover:opacity-100 transition-opacity z-20 pointer-events-none w-32 left-1/2 -translate-x-1/2 text-center">
                      <p>Pred: {predictedPct.toFixed(1)}%</p>
                      <p>Actual: {actualPct.toFixed(1)}%</p>
                      <p className="text-fintrix-text-dimmed text-[10px]">n={band.count}</p>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex justify-between px-2 mt-2 text-[10px] text-fintrix-text-dimmed">
              {calibration.calibration_curve.map((b: any) => (
                <span key={b.confidence_range} className="flex-1 text-center">{b.confidence_range}</span>
              ))}
            </div>
            <p className="text-center text-xs text-fintrix-text-muted mt-2">Predicted Confidence Range</p>
          </div>
        )}

        {/* Threshold Sensitivity */}
        {sensitivity && (
          <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
            <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
              <span className="text-emerald-400">🎛️</span> Threshold Sensitivity
            </h3>
            
            {/* Slider */}
            <div className="mb-6 bg-fintrix-surface-2/50 p-4 rounded-lg border border-fintrix-border/50">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-fintrix-text">Auto-Resolve Threshold</span>
                <span className="text-sm font-mono text-emerald-400 font-bold">{sliderThreshold.toFixed(2)}</span>
              </div>
              <input 
                type="range" 
                min="0.5" 
                max="1.0" 
                step="0.05"
                value={sliderThreshold}
                onChange={(e) => setSliderThreshold(parseFloat(e.target.value))}
                className="w-full accent-emerald-500 h-2 bg-fintrix-surface-2 rounded-lg appearance-none cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-fintrix-text-dimmed mt-1">
                <span>0.50 (Aggressive)</span>
                <span>1.00 (Conservative)</span>
              </div>
            </div>

            {/* Selected Data */}
            {(() => {
              const currentData = sensitivity.sensitivity_curve.find((s: any) => Math.abs(s.threshold - sliderThreshold) < 0.01);
              if (!currentData) return null;
              
              return (
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-fintrix-surface-2/30 rounded-lg border border-fintrix-border/30 text-center">
                    <p className="text-xs text-fintrix-text-muted mb-1">Auto-Resolve Rate</p>
                    <p className="text-2xl font-bold text-emerald-400">{(currentData.auto_resolve_rate * 100).toFixed(1)}%</p>
                    <p className="text-[10px] text-fintrix-text-dimmed mt-1">
                      {currentData.auto_resolve_count} of {sensitivity.total_investigations}
                    </p>
                  </div>
                  <div className="p-4 bg-fintrix-surface-2/30 rounded-lg border border-fintrix-border/30 text-center">
                    <p className="text-xs text-fintrix-text-muted mb-1">Estimated Error Rate</p>
                    <p className={`text-2xl font-bold ${currentData.estimated_error_rate > 0.05 ? 'text-red-400' : 'text-amber-400'}`}>
                      {(currentData.estimated_error_rate * 100).toFixed(1)}%
                    </p>
                    <p className="text-[10px] text-fintrix-text-dimmed mt-1">
                      {currentData.estimated_error_count} errors expected
                    </p>
                  </div>
                </div>
              );
            })()}
            
          </div>
        )}
      </div>

    </div>
  );
}
