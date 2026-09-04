import { useState, useEffect } from "react";
import { api, type TrendData, type SLAData, type ROIData } from "../api";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { chartColors, ChartTooltip, axisTickStyle } from "./theme";

/** Compact horizontal P50/P95/P99 bar — replaces a plain number list with an
 * actual visual so latency cards match the rest of the charted sections. */
function LatencyBarGroup({
  items,
  unitFmt,
}: {
  items: { label: string; value: number | null; color: string }[];
  unitFmt: (v: number) => string;
}) {
  const data = items
    .filter((i) => i.value != null)
    .map((i) => ({ label: i.label, value: i.value as number, color: i.color }));
  if (data.length === 0)
    return <p className="text-xs text-fintrix-text-dimmed">No data yet</p>;
  return (
    <ResponsiveContainer width="100%" height={90}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ left: 4, right: 12, top: 0, bottom: 0 }}
      >
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="label"
          tick={axisTickStyle}
          axisLine={false}
          tickLine={false}
          width={28}
        />
        <Tooltip
          content={
            <ChartTooltip formatter={(v) => [unitFmt(v as number), ""]} />
          }
          cursor={{ fill: "rgba(255,255,255,0.03)" }}
        />
        <Bar
          dataKey="value"
          radius={[0, 3, 3, 0]}
          barSize={14}
          animationDuration={500}
        >
          {data.map((d, i) => (
            <Cell key={i} fill={d.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Placeholder shown instead of silently omitting a card when its endpoint
 * returned no data yet (e.g. before the first reconciliation run) — keeps the
 * page looking intentional rather than broken mid-demo. */
function EmptyCard({
  icon,
  title,
  hint,
}: {
  icon: string;
  title: string;
  hint: string;
}) {
  return (
    <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle border-dashed flex flex-col items-center justify-center text-center min-h-[180px]">
      <span
        className="material-symbols-outlined text-fintrix-text-dimmed mb-2"
        style={{ fontSize: "28px" }}
      >
        {icon}
      </span>
      <p className="text-sm font-medium text-fintrix-text-muted">{title}</p>
      <p className="text-xs text-fintrix-text-dimmed mt-1 max-w-xs">{hint}</p>
    </div>
  );
}

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
  const [refreshing, setRefreshing] = useState(false);
  const [period, setPeriod] = useState(30);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    loadData();
  }, [period]);

  const loadData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
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
      const val = (r: PromiseSettledResult<any>) =>
        r.status === "fulfilled" ? r.value : null;
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
      setRefreshing(false);
      setLastUpdated(new Date());
    }
  };

  const fmt = (n?: number | null) =>
    n != null ? n.toLocaleString("en-IN") : "0";
  const fmtPct = (n?: number | null) =>
    n != null ? `${(n * 100).toFixed(1)}%` : "0.0%";

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-fintrix-primary/30 border-t-fintrix-primary rounded-full animate-spin mx-auto mb-3" />
          <p className="text-fintrix-text-muted text-sm">
            Loading analytics...
          </p>
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
          <p className="text-fintrix-text-muted text-sm mt-1">
            Trends, SLA tracking & ROI analysis
            {lastUpdated && (
              <span className="text-fintrix-text-dimmed">
                {" "}
                · updated {lastUpdated.toLocaleTimeString("en-IN")}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-fintrix-text-muted hover:bg-fintrix-surface-2 hover:text-fintrix-text transition-all cursor-pointer disabled:opacity-50"
            title="Refresh"
          >
            <span
              className={`material-symbols-outlined ${refreshing ? "animate-spin" : ""}`}
              style={{ fontSize: "18px" }}
            >
              refresh
            </span>
          </button>
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
      </div>

      {/* ROI Summary Cards */}
      {roi && (
        <div className="grid grid-cols-4 gap-4">
          <div className="glass-card rounded-xl p-5 border border-fintrix-border-subtle">
            <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">
              Auto-Resolve Rate
            </p>
            <p className="text-3xl font-bold text-emerald-400">
              {roi.auto_resolve_rate}%
            </p>
            <p className="text-xs text-fintrix-text-dimmed mt-1">
              {fmt(roi.auto_resolved)} of {fmt(roi.total_exceptions)}
            </p>
          </div>
          <div className="glass-card rounded-xl p-5 border border-fintrix-border-subtle">
            <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">
              Hours Saved
            </p>
            <p className="text-3xl font-bold text-blue-400">
              {fmt(roi.time_savings.total_hours_saved)}
            </p>
            <p className="text-xs text-fintrix-text-dimmed mt-1">
              {fmt(roi.time_savings.reconciliation_hours)}h recon +{" "}
              {fmt(roi.time_savings.investigation_hours)}h investigation
            </p>
          </div>
          <div className="glass-card rounded-xl p-5 border border-fintrix-border-subtle">
            <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">
              Cost Saved
            </p>
            <p className="text-3xl font-bold text-amber-400">
              ₹{fmt(roi.cost_savings.total_saved_rupees)}
            </p>
            <p className="text-xs text-fintrix-text-dimmed mt-1">
              @ ₹{roi.cost_savings.hourly_rate}/hr
            </p>
          </div>
          <div className="glass-card rounded-xl p-5 border border-fintrix-border-subtle">
            <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">
              AI Speedup
            </p>
            <p className="text-3xl font-bold text-violet-400">
              {roi.accuracy.speedup_factor ?? "—"}x
            </p>
            <p className="text-xs text-fintrix-text-dimmed mt-1">
              vs {roi.accuracy.manual_time_per_exception_min}min manual
            </p>
          </div>
        </div>
      )}

      {/* SLA Metrics */}
      {sla && (
        <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
          <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
            <span
              className="material-symbols-outlined text-amber-400"
              style={{ fontSize: "20px" }}
            >
              timer
            </span>{" "}
            SLA Performance
          </h3>
          <div className="grid grid-cols-3 gap-6">
            <div>
              <p className="text-sm text-fintrix-text-muted mb-3 font-medium">
                AI Investigation Latency
              </p>
              <LatencyBarGroup
                items={[
                  {
                    label: "P50",
                    value: sla.investigation_latency_ms.p50,
                    color: chartColors.success,
                  },
                  {
                    label: "P95",
                    value: sla.investigation_latency_ms.p95,
                    color: chartColors.warning,
                  },
                  {
                    label: "P99",
                    value: sla.investigation_latency_ms.p99,
                    color: chartColors.danger,
                  },
                ]}
                unitFmt={(v) => `${fmt(v)}ms`}
              />
            </div>
            <div>
              <p className="text-sm text-fintrix-text-muted mb-3 font-medium">
                Time to Resolve
              </p>
              <LatencyBarGroup
                items={[
                  {
                    label: "P50",
                    value: sla.time_to_resolve_seconds.p50,
                    color: chartColors.success,
                  },
                  {
                    label: "P95",
                    value: sla.time_to_resolve_seconds.p95,
                    color: chartColors.warning,
                  },
                  {
                    label: "P99",
                    value: sla.time_to_resolve_seconds.p99,
                    color: chartColors.danger,
                  },
                ]}
                unitFmt={(v) => (v < 60 ? `${v}s` : `${(v / 60).toFixed(1)}m`)}
              />
            </div>
            <div>
              <p className="text-sm text-fintrix-text-muted mb-3 font-medium">
                Reconciliation Duration
              </p>
              <LatencyBarGroup
                items={[
                  {
                    label: "P50",
                    value: sla.reconciliation_duration_ms.p50,
                    color: chartColors.success,
                  },
                  {
                    label: "P95",
                    value: sla.reconciliation_duration_ms.p95,
                    color: chartColors.warning,
                  },
                  {
                    label: "P99",
                    value: sla.reconciliation_duration_ms.p99,
                    color: chartColors.danger,
                  },
                ]}
                unitFmt={(v) => `${fmt(v)}ms`}
              />
              <div className="mt-3 pt-3 border-t border-fintrix-border-subtle">
                <div className="flex justify-between text-xs">
                  <span className="text-fintrix-text-dimmed">Throughput</span>
                  <span className="text-fintrix-text-muted font-mono">
                    {fmt(sla.throughput.total_records_processed)} records
                  </span>
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
              <span
                className="material-symbols-outlined text-emerald-400"
                style={{ fontSize: "20px" }}
              >
                trending_up
              </span>{" "}
              Accuracy Trend
            </h3>
            {trends.run_trends.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart
                  data={trends.run_trends.slice(-10).map((r) => ({
                    date: r.date?.split("T")[0]?.slice(5) ?? "—",
                    accuracy: +(r.accuracy * 100).toFixed(1),
                  }))}
                >
                  <defs>
                    <linearGradient
                      id="gradSuccess"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="0%"
                        stopColor={chartColors.success}
                        stopOpacity={0.45}
                      />
                      <stop
                        offset="100%"
                        stopColor={chartColors.success}
                        stopOpacity={0.02}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    stroke={chartColors.grid}
                    strokeDasharray="3 3"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="date"
                    tick={axisTickStyle}
                    axisLine={{ stroke: chartColors.grid }}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={axisTickStyle}
                    axisLine={false}
                    tickLine={false}
                    width={32}
                    unit="%"
                  />
                  <Tooltip
                    content={
                      <ChartTooltip formatter={(v) => [`${v}%`, "Accuracy"]} />
                    }
                  />
                  <Area
                    type="monotone"
                    dataKey="accuracy"
                    stroke={chartColors.success}
                    strokeWidth={2}
                    fill="url(#gradSuccess)"
                    dot={{ r: 3, fill: chartColors.success, strokeWidth: 0 }}
                    activeDot={{ r: 5 }}
                    animationDuration={600}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-fintrix-text-dimmed">
                No runs yet. Run the pipeline to see trends.
              </p>
            )}
            <div className="mt-4 pt-4 border-t border-fintrix-border-subtle">
              <div className="flex justify-between text-xs">
                <span className="text-fintrix-text-dimmed">
                  Average Accuracy
                </span>
                <span className="text-emerald-400 font-medium">
                  {fmtPct(trends.summary.avg_accuracy)}
                </span>
              </div>
            </div>
          </div>

          {/* Exception Volume */}
          <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
            <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
              <span
                className="material-symbols-outlined text-red-400"
                style={{ fontSize: "20px" }}
              >
                bar_chart
              </span>{" "}
              Exception Volume
            </h3>
            {trends.exception_trends.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart
                  data={trends.exception_trends.slice(-10).map((e) => ({
                    date: e.date?.slice(5) ?? e.date,
                    Resolved: e.resolved,
                    Escalated: e.escalated,
                    Pending: e.total - e.resolved - e.escalated,
                  }))}
                  barCategoryGap={6}
                >
                  <CartesianGrid
                    stroke={chartColors.grid}
                    strokeDasharray="3 3"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="date"
                    tick={axisTickStyle}
                    axisLine={{ stroke: chartColors.grid }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={axisTickStyle}
                    axisLine={false}
                    tickLine={false}
                    width={24}
                    allowDecimals={false}
                  />
                  <Tooltip
                    content={<ChartTooltip />}
                    cursor={{ fill: "rgba(255,255,255,0.03)" }}
                  />
                  <Bar
                    dataKey="Resolved"
                    stackId="s"
                    fill={chartColors.success}
                    radius={[0, 0, 0, 0]}
                  />
                  <Bar
                    dataKey="Escalated"
                    stackId="s"
                    fill={chartColors.warning}
                    radius={[0, 0, 0, 0]}
                  />
                  <Bar
                    dataKey="Pending"
                    stackId="s"
                    fill={chartColors.danger}
                    radius={[3, 3, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-fintrix-text-dimmed">
                No exception data yet.
              </p>
            )}
            <div className="mt-4 pt-4 border-t border-fintrix-border-subtle flex gap-4 text-[10px]">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />{" "}
                Resolved
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-amber-500" /> Escalated
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-red-500" /> Pending
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ROI Detailed Card */}
      {roi && (
        <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
          <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
            <span
              className="material-symbols-outlined text-emerald-400"
              style={{ fontSize: "20px" }}
            >
              savings
            </span>{" "}
            ROI Calculator
          </h3>
          <div className="grid grid-cols-3 gap-8">
            <div className="space-y-3">
              <h4 className="text-xs text-fintrix-text-muted uppercase tracking-wider font-medium">
                Processing Volume
              </h4>
              <div className="flex justify-between">
                <span className="text-sm text-fintrix-text-dimmed">
                  Records Processed
                </span>
                <span className="text-sm font-mono text-fintrix-text">
                  {fmt(roi.total_records_processed)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-fintrix-text-dimmed">
                  Exceptions Detected
                </span>
                <span className="text-sm font-mono text-fintrix-text">
                  {fmt(roi.total_exceptions)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-fintrix-text-dimmed">
                  Auto-Resolved
                </span>
                <span className="text-sm font-mono text-emerald-400">
                  {fmt(roi.auto_resolved)}
                </span>
              </div>
            </div>
            <div className="space-y-3">
              <h4 className="text-xs text-fintrix-text-muted uppercase tracking-wider font-medium">
                Time Savings
              </h4>
              <div className="flex justify-between">
                <span className="text-sm text-fintrix-text-dimmed">
                  Reconciliation
                </span>
                <span className="text-sm font-mono text-fintrix-text">
                  {roi.time_savings.reconciliation_hours}h
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-fintrix-text-dimmed">
                  Investigation
                </span>
                <span className="text-sm font-mono text-fintrix-text">
                  {roi.time_savings.investigation_hours}h
                </span>
              </div>
              <div className="flex justify-between border-t border-fintrix-border-subtle pt-2">
                <span className="text-sm text-fintrix-text-muted font-medium">
                  Total Saved
                </span>
                <span className="text-sm font-mono text-blue-400 font-bold">
                  {roi.time_savings.total_hours_saved}h
                </span>
              </div>
            </div>
            <div className="space-y-3">
              <h4 className="text-xs text-fintrix-text-muted uppercase tracking-wider font-medium">
                Financial Impact
              </h4>
              <div className="flex justify-between">
                <span className="text-sm text-fintrix-text-dimmed">
                  Cost Saved
                </span>
                <span className="text-sm font-mono text-emerald-400">
                  ₹{fmt(roi.cost_savings.total_saved_rupees)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-fintrix-text-dimmed">
                  Risk Resolved
                </span>
                <span className="text-sm font-mono text-fintrix-text">
                  ₹{fmt(roi.amount_at_risk_resolved_rupees)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-fintrix-text-dimmed">
                  AI Latency
                </span>
                <span className="text-sm font-mono text-violet-400">
                  {roi.accuracy.avg_ai_latency_ms ?? "—"}ms
                </span>
              </div>
            </div>
          </div>

          {/* Manual vs. Fintrix time comparison — the single clearest "why this matters"
              visual. Automated hours are estimated from actual AI latency × exception
              count (near-zero for rule-resolved cases); manual hours = automated + saved,
              since total_hours_saved is defined as (manual - automated). Both bars are
              derived from real ROI fields, not invented numbers. */}
          {(() => {
            const automatedHours = roi.accuracy.avg_ai_latency_ms
              ? +(
                  (roi.accuracy.avg_ai_latency_ms * roi.total_exceptions) /
                  1000 /
                  3600
                ).toFixed(2)
              : 0.01;
            const manualHours = +(
              roi.time_savings.total_hours_saved + automatedHours
            ).toFixed(2);
            const compData = [
              {
                label: "Manual process (est.)",
                hours: manualHours,
                fill: chartColors.textMuted,
              },
              {
                label: "With Fintrix",
                hours: automatedHours,
                fill: chartColors.success,
              },
            ];
            return (
              <div className="mt-6 pt-6 border-t border-fintrix-border-subtle">
                <h4 className="text-xs text-fintrix-text-muted uppercase tracking-wider font-medium mb-3">
                  Manual Process vs. Fintrix — Hours to Process This Batch
                </h4>
                <ResponsiveContainer width="100%" height={90}>
                  <BarChart
                    data={compData}
                    layout="vertical"
                    margin={{ left: 4, right: 40, top: 0, bottom: 0 }}
                  >
                    <XAxis type="number" hide />
                    <YAxis
                      type="category"
                      dataKey="label"
                      tick={axisTickStyle}
                      axisLine={false}
                      tickLine={false}
                      width={130}
                    />
                    <Tooltip
                      content={
                        <ChartTooltip formatter={(v) => [`${v}h`, ""]} />
                      }
                      cursor={{ fill: "rgba(255,255,255,0.03)" }}
                    />
                    <Bar
                      dataKey="hours"
                      radius={[0, 4, 4, 0]}
                      barSize={20}
                      animationDuration={600}
                    >
                      {compData.map((d, i) => (
                        <Cell key={i} fill={d.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            );
          })()}
        </div>
      )}

      {/* Cash Forecast */}
      {forecast ? (
        <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
          <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
            <span
              className="material-symbols-outlined text-blue-400"
              style={{ fontSize: "20px" }}
            >
              show_chart
            </span>{" "}
            Cash Flow Forecast (Next {forecast.forecast_days} Days)
          </h3>
          <div className="grid grid-cols-3 gap-6 mb-6">
            <div>
              <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">
                Projected Inflow
              </p>
              <p className="text-2xl font-bold text-blue-400">
                ₹{fmt(forecast.summary?.total_predicted_rupees)}
              </p>
            </div>
            <div>
              <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">
                Pending Settlements
              </p>
              <p className="text-2xl font-bold text-fintrix-text">
                ₹{fmt(forecast.summary?.total_pending_rupees)}
              </p>
            </div>
            <div>
              <p className="text-xs text-fintrix-text-muted uppercase tracking-wider mb-1">
                Trend
              </p>
              <p
                className={`text-2xl font-bold ${forecast.summary?.trend_direction === "up" ? "text-emerald-400" : "text-amber-400"}`}
              >
                {forecast.summary?.trend_direction === "up" ? "↑" : "↓"}{" "}
                {forecast.summary?.trend_direction ?? "stable"}
              </p>
            </div>
          </div>

          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={forecast.daily_forecast?.map((d: any) => ({
                date: d.date.split("-").slice(1).join("/"),
                projected: d.predicted_amount_rupees,
              }))}
            >
              <defs>
                <linearGradient id="gradForecast" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={chartColors.primaryLight} />
                  <stop
                    offset="100%"
                    stopColor={chartColors.primary}
                    stopOpacity={0.5}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid
                stroke={chartColors.grid}
                strokeDasharray="3 3"
                vertical={false}
              />
              <XAxis
                dataKey="date"
                tick={axisTickStyle}
                axisLine={{ stroke: chartColors.grid }}
                tickLine={false}
              />
              <YAxis
                tick={axisTickStyle}
                axisLine={false}
                tickLine={false}
                width={44}
                tickFormatter={(v: any) =>
                  v >= 1000 ? `₹${(v / 1000).toFixed(0)}K` : `₹${v}`
                }
              />
              <Tooltip
                content={
                  <ChartTooltip
                    formatter={(v) => [`₹${fmt(v)}`, "Projected"]}
                  />
                }
                cursor={{ fill: "rgba(255,255,255,0.03)" }}
              />
              <Bar
                dataKey="projected"
                fill="url(#gradForecast)"
                radius={[4, 4, 0, 0]}
                animationDuration={600}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <EmptyCard
          icon="show_chart"
          title="No cash flow forecast yet"
          hint="Run a reconciliation to project inflows for the next 14 days."
        />
      )}

      {/* Tax Reconciliation */}
      {tax ? (
        <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
          <div className="flex justify-between items-start mb-4">
            <h3 className="text-lg font-semibold text-fintrix-text flex items-center gap-2">
              <span
                className="material-symbols-outlined text-amber-400"
                style={{ fontSize: "20px" }}
              >
                gavel
              </span>{" "}
              Tax & Fee Reconciliation
            </h3>
            <div className="text-right">
              <p className="text-xs text-fintrix-text-muted uppercase tracking-wider">
                Total Discrepancy
              </p>
              <p className="text-xl font-bold text-amber-400">
                ₹
                {fmt(
                  tax.totals.fee_difference_rupees +
                    tax.totals.gst_difference_rupees,
                )}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div>
              <h4 className="text-sm font-medium text-fintrix-text-muted mb-3">
                Match Breakdown
              </h4>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-fintrix-text flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />{" "}
                    Exact Match
                  </span>
                  <span className="text-sm font-mono text-fintrix-text">
                    {tax.summary.exact_matches}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-fintrix-text flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-blue-400" />{" "}
                    Rounding Diff
                  </span>
                  <span className="text-sm font-mono text-fintrix-text">
                    {tax.summary.rounding_differences}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-fintrix-text flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-amber-400" /> Rate
                    Change
                  </span>
                  <span className="text-sm font-mono text-fintrix-text">
                    {tax.summary.rate_changes}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-fintrix-text flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-red-400" />{" "}
                    Unexplained
                  </span>
                  <span className="text-sm font-mono text-fintrix-text">
                    {tax.summary.unexplained_discrepancies}
                  </span>
                </div>
              </div>
            </div>

            <div>
              <h4 className="text-sm font-medium text-fintrix-text-muted mb-3">
                Discrepancy Details
              </h4>
              <div className="space-y-3 p-4 bg-fintrix-surface-2/50 rounded-lg border border-fintrix-border/50">
                <div className="flex justify-between">
                  <span className="text-xs text-fintrix-text-dimmed">
                    Total Transactions
                  </span>
                  <span className="text-xs font-mono">
                    {tax.summary.total_transactions}
                  </span>
                </div>
                <div className="flex justify-between border-t border-fintrix-border-subtle pt-2">
                  <span className="text-xs text-fintrix-text-dimmed">
                    Fee Discrepancy
                  </span>
                  <span className="text-xs font-mono text-amber-400">
                    ₹{fmt(tax.summary.total_fee_difference_rupees)}
                  </span>
                </div>
                <div className="flex justify-between border-t border-fintrix-border-subtle pt-2">
                  <span className="text-xs text-fintrix-text-dimmed">
                    GST Discrepancy
                  </span>
                  <span className="text-xs font-mono text-red-400">
                    ₹{fmt(tax.summary.total_gst_difference_rupees)}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <EmptyCard
          icon="gavel"
          title="No tax reconciliation data yet"
          hint="Run a reconciliation to see MDR/GST discrepancy analysis."
        />
      )}

      {/* AI Performance & Sensitivity Grid */}
      <div className="grid grid-cols-2 gap-6">
        {/* Confidence Calibration */}
        {calibration ? (
          <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
            <div className="flex justify-between items-start mb-6">
              <h3 className="text-lg font-semibold text-fintrix-text flex items-center gap-2">
                <span
                  className="material-symbols-outlined text-violet-400"
                  style={{ fontSize: "20px" }}
                >
                  target
                </span>{" "}
                Confidence Calibration
              </h3>
              <div className="text-right">
                <p className="text-xs text-fintrix-text-muted uppercase tracking-wider">
                  ECE Score
                </p>
                <p
                  className={`text-xl font-bold ${
                    calibration.ece_interpretation === "excellent"
                      ? "text-emerald-400"
                      : calibration.ece_interpretation === "good"
                        ? "text-blue-400"
                        : calibration.ece_interpretation === "fair"
                          ? "text-amber-400"
                          : "text-red-400"
                  }`}
                >
                  {calibration.ece.toFixed(4)}
                </p>
              </div>
            </div>

            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart
                data={calibration.calibration_curve
                  ?.filter((b: any) => b.count > 0)
                  .map((b: any) => ({
                    range: b.confidence_range,
                    predicted: +(b.predicted_confidence * 100).toFixed(1),
                    actual: +(b.actual_accuracy * 100).toFixed(1),
                    n: b.count,
                  }))}
              >
                <CartesianGrid
                  stroke={chartColors.grid}
                  strokeDasharray="3 3"
                  vertical={false}
                />
                <XAxis
                  dataKey="range"
                  tick={axisTickStyle}
                  axisLine={{ stroke: chartColors.grid }}
                  tickLine={false}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={axisTickStyle}
                  axisLine={false}
                  tickLine={false}
                  width={32}
                  unit="%"
                />
                <Tooltip
                  content={
                    <ChartTooltip
                      formatter={(v, n) => [
                        `${v}%`,
                        n === "actual" ? "Actual accuracy" : "Predicted",
                      ]}
                    />
                  }
                  cursor={{ fill: "rgba(255,255,255,0.03)" }}
                />
                {/* Perfect-calibration reference: actual should track predicted exactly */}
                <Line
                  type="monotone"
                  dataKey="predicted"
                  stroke="rgba(255,255,255,0.35)"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  dot={false}
                  name="Ideal (predicted)"
                />
                <Bar
                  dataKey="actual"
                  fill={chartColors.ai}
                  radius={[3, 3, 0, 0]}
                  name="actual"
                  animationDuration={600}
                />
              </ComposedChart>
            </ResponsiveContainer>
            <p className="text-center text-xs text-fintrix-text-muted mt-2">
              Purple bars = actual accuracy · dashed line = perfect calibration
              (predicted = actual)
            </p>
          </div>
        ) : (
          <EmptyCard
            icon="target"
            title="No calibration data yet"
            hint="Needs enough resolved investigations with ground truth to compute."
          />
        )}

        {/* Threshold Sensitivity */}
        {sensitivity ? (
          <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle">
            <h3 className="text-lg font-semibold text-fintrix-text mb-4 flex items-center gap-2">
              <span
                className="material-symbols-outlined text-emerald-400"
                style={{ fontSize: "20px" }}
              >
                tune
              </span>{" "}
              Threshold Sensitivity
            </h3>

            {/* Slider */}
            <div className="mb-6 bg-fintrix-surface-2/50 p-4 rounded-lg border border-fintrix-border/50">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-fintrix-text">
                  Auto-Resolve Threshold
                </span>
                <span className="text-sm font-mono text-emerald-400 font-bold">
                  {sliderThreshold.toFixed(2)}
                </span>
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

            {/* Full tradeoff curve — auto-resolve rate vs. estimated error rate across all
                thresholds, with the current slider position marked. Makes the guardrail
                tradeoff visible at a glance instead of only showing one point at a time. */}
            <ResponsiveContainer width="100%" height={140}>
              <ComposedChart
                data={sensitivity.sensitivity_curve.map((s: any) => ({
                  threshold: s.threshold.toFixed(2),
                  thresholdVal: s.threshold,
                  autoResolve: +(s.auto_resolve_rate * 100).toFixed(1),
                  errorRate: +(s.estimated_error_rate * 100).toFixed(1),
                }))}
              >
                <CartesianGrid
                  stroke={chartColors.grid}
                  strokeDasharray="3 3"
                  vertical={false}
                />
                <XAxis
                  dataKey="threshold"
                  tick={axisTickStyle}
                  axisLine={{ stroke: chartColors.grid }}
                  tickLine={false}
                />
                <YAxis
                  tick={axisTickStyle}
                  axisLine={false}
                  tickLine={false}
                  width={30}
                  unit="%"
                />
                <Tooltip
                  content={
                    <ChartTooltip
                      formatter={(v, n) => [
                        `${v}%`,
                        n === "autoResolve"
                          ? "Auto-resolve rate"
                          : "Est. error rate",
                      ]}
                    />
                  }
                />
                <Line
                  type="monotone"
                  dataKey="autoResolve"
                  stroke={chartColors.success}
                  strokeWidth={2}
                  dot={false}
                  name="autoResolve"
                />
                <Line
                  type="monotone"
                  dataKey="errorRate"
                  stroke={chartColors.danger}
                  strokeWidth={2}
                  dot={false}
                  name="errorRate"
                />
                <ReferenceLine
                  x={sliderThreshold.toFixed(2)}
                  stroke={chartColors.textMuted}
                  strokeDasharray="3 3"
                />
              </ComposedChart>
            </ResponsiveContainer>
            <div className="flex gap-4 text-[10px] text-fintrix-text-dimmed mt-1 mb-4 justify-center">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />{" "}
                Auto-resolve rate
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-red-500" /> Estimated
                error rate
              </span>
            </div>

            {/* Selected Data */}
            {(() => {
              const currentData = sensitivity.sensitivity_curve.find(
                (s: any) => Math.abs(s.threshold - sliderThreshold) < 0.01,
              );
              if (!currentData) return null;

              return (
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-fintrix-surface-2/30 rounded-lg border border-fintrix-border/30 text-center">
                    <p className="text-xs text-fintrix-text-muted mb-1">
                      Auto-Resolve Rate
                    </p>
                    <p className="text-2xl font-bold text-emerald-400">
                      {(currentData.auto_resolve_rate * 100).toFixed(1)}%
                    </p>
                    <p className="text-[10px] text-fintrix-text-dimmed mt-1">
                      {currentData.auto_resolve_count} of{" "}
                      {sensitivity.total_investigations}
                    </p>
                  </div>
                  <div className="p-4 bg-fintrix-surface-2/30 rounded-lg border border-fintrix-border/30 text-center">
                    <p className="text-xs text-fintrix-text-muted mb-1">
                      Estimated Error Rate
                    </p>
                    <p
                      className={`text-2xl font-bold ${currentData.estimated_error_rate > 0.05 ? "text-red-400" : "text-amber-400"}`}
                    >
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
        ) : (
          <EmptyCard
            icon="tune"
            title="No sensitivity data yet"
            hint="Needs resolved investigations to model the confidence/error tradeoff."
          />
        )}
      </div>
    </div>
  );
}
