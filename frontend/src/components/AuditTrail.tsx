import { useState, useEffect, useCallback } from "react";
import { api, type AuditLogEntry, type AuditStats } from "../api";

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatTimestamp(ts: string): string {
  return new Date(ts).toLocaleString("en-IN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// ── Actor Badge ──────────────────────────────────────────────────────────────
function ActorBadge({ actor }: { actor: string }) {
  const config: Record<string, { bg: string; icon: string; label: string }> = {
    system: { bg: "bg-slate-500/12 text-slate-400 border-slate-500/25", icon: "settings", label: "System" },
    ai_investigator: { bg: "bg-purple-500/12 text-purple-400 border-purple-500/25", icon: "smart_toy", label: "AI" },
    human: { bg: "bg-blue-500/12 text-blue-400 border-blue-500/25", icon: "person", label: "Human" },
  };
  const c = config[actor] || config.system;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-[11px] font-semibold ${c.bg}`}>
      <span className="material-symbols-outlined" style={{ fontSize: "13px" }}>{c.icon}</span>
      {c.label}
    </span>
  );
}

// ── Action Badge ─────────────────────────────────────────────────────────────
function ActionBadge({ action }: { action: string }) {
  const colorMap: Record<string, string> = {
    csv_uploaded: "text-blue-400",
    synthetic_data_generated: "text-blue-400",
    started: "text-amber-400",
    completed: "text-emerald-400",
    detected: "text-amber-400",
    investigated: "text-purple-400",
    investigation_started: "text-purple-400",
    investigation_failed: "text-red-400",
    investigation_error: "text-red-400",
    manual_approve: "text-emerald-400",
    manual_reject: "text-red-400",
    manual_escalate: "text-amber-400",
    bulk_approve: "text-emerald-400",
    bulk_escalate: "text-amber-400",
    event_received: "text-cyan-400",
    ingested_via_webhook: "text-cyan-400",
  };
  return (
    <span className={`text-xs font-semibold ${colorMap[action] || "text-fintrix-text-muted"}`}>
      {action.replace(/_/g, " ")}
    </span>
  );
}

// ── Stats Card ───────────────────────────────────────────────────────────────
function StatCard({ label, value, icon }: { label: string; value: number; icon: string }) {
  return (
    <div className="glass-card glass-card-hover p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="material-symbols-outlined opacity-40" style={{ fontSize: "18px" }}>{icon}</span>
        <span className="text-[11px] text-fintrix-text-muted uppercase tracking-wider font-medium">{label}</span>
      </div>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
}

// ── State Diff Viewer ────────────────────────────────────────────────────────
function StateDiffViewer({ oldState, newState }: { oldState: Record<string, unknown> | null; newState: Record<string, unknown> | null }) {
  if (!oldState && !newState) return <span className="text-fintrix-text-dimmed">—</span>;

  const allKeys = new Set([
    ...Object.keys(oldState || {}),
    ...Object.keys(newState || {}),
  ]);

  const changes: { key: string; before: unknown; after: unknown; changed: boolean }[] = [];
  allKeys.forEach((key) => {
    const before = oldState?.[key];
    const after = newState?.[key];
    changes.push({ key, before, after, changed: JSON.stringify(before) !== JSON.stringify(after) });
  });

  if (changes.length === 0) return <span className="text-fintrix-text-dimmed">—</span>;

  return (
    <div className="bg-fintrix-surface-2/50 rounded-lg p-3 border border-fintrix-border-subtle space-y-1.5">
      {changes.slice(0, 6).map((c) => (
        <div key={c.key} className="flex items-start gap-2 text-[11px] font-mono">
          <span className="text-fintrix-text-muted shrink-0 min-w-[80px]">{c.key}:</span>
          {c.changed ? (
            <div className="flex gap-2 flex-wrap">
              {c.before !== undefined && (
                <span className="text-red-400/80 line-through">
                  {typeof c.before === "object" ? "..." : String(c.before)}
                </span>
              )}
              <span className="text-fintrix-text-muted">→</span>
              <span className="text-emerald-400">
                {typeof c.after === "object" ? "..." : String(c.after)}
              </span>
            </div>
          ) : (
            <span className="text-fintrix-text-dimmed">
              {typeof c.after === "object" ? "..." : String(c.after ?? c.before)}
            </span>
          )}
        </div>
      ))}
      {changes.length > 6 && (
        <p className="text-[10px] text-fintrix-text-dimmed">+{changes.length - 6} more fields</p>
      )}
    </div>
  );
}

// ── Timeline Entry ───────────────────────────────────────────────────────────
function TimelineEntry({ log, expanded, onToggle }: { log: AuditLogEntry; expanded: boolean; onToggle: () => void }) {
  const actorClasses: Record<string, string> = {
    system: "timeline-node-system",
    ai_investigator: "timeline-node-ai",
    human: "timeline-node-human",
  };

  return (
    <div className={`timeline-node ${actorClasses[log.actor] || "timeline-node-system"}`}>
      <div
        className="cursor-pointer hover:bg-fintrix-surface-2/30 rounded-lg p-2 -m-2 transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <ActorBadge actor={log.actor} />
            <ActionBadge action={log.action} />
          </div>
          <span className="text-[10px] text-fintrix-text-dimmed font-mono" title={formatTimestamp(log.timestamp)}>
            {timeAgo(log.timestamp)}
          </span>
        </div>

        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-[11px] font-mono text-fintrix-text-muted">
            <span className="text-fintrix-text">{log.entity_type}</span>
            <span className="text-fintrix-text-dimmed mx-1">:</span>
            <span>{log.entity_id}</span>
          </span>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 animate-fade-in">
          <StateDiffViewer oldState={log.old_state} newState={log.new_state} />
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Audit Trail Page
// ═══════════════════════════════════════════════════════════════════════════════
export default function AuditTrail() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [filterEntity, setFilterEntity] = useState<string>("");
  const [filterActor, setFilterActor] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<"timeline" | "table">("timeline");
  const [displayLimit, setDisplayLimit] = useState(25);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { limit: 200 };
      if (filterEntity) params.entity_type = filterEntity;
      if (filterActor) params.actor = filterActor;
      const [data, statsData] = await Promise.all([
        api.listAuditLogs(params),
        api.getAuditStats(),
      ]);
      setLogs(data);
      setStats(statsData);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [filterEntity, filterActor]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Audit Trail</h2>
          <p className="text-sm text-fintrix-text-muted mt-1.5">
            Immutable, append-only log of every action, decision, and state change
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setViewMode("timeline")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-all ${
              viewMode === "timeline"
                ? "bg-fintrix-primary/15 text-fintrix-primary border border-fintrix-primary/30"
                : "bg-fintrix-surface-2/50 text-fintrix-text-muted border border-fintrix-border-subtle"
            }`}
          >
            Timeline
          </button>
          <button
            onClick={() => setViewMode("table")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-all ${
              viewMode === "table"
                ? "bg-fintrix-primary/15 text-fintrix-primary border border-fintrix-primary/30"
                : "bg-fintrix-surface-2/50 text-fintrix-text-muted border border-fintrix-border-subtle"
            }`}
          >
            Table
          </button>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 stagger-children">
          <StatCard label="Total Entries" value={stats.total} icon="list_alt" />
          <StatCard label="System Actions" value={stats.by_actor.system || 0} icon="settings" />
          <StatCard label="AI Actions" value={stats.by_actor.ai_investigator || 0} icon="smart_toy" />
          <StatCard label="Human Actions" value={stats.by_actor.human || 0} icon="person" />
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <select
          value={filterEntity}
          onChange={(e) => setFilterEntity(e.target.value)}
          className="bg-fintrix-surface border border-fintrix-border rounded-lg px-3 py-2 text-sm text-fintrix-text focus:border-fintrix-primary outline-none cursor-pointer"
        >
          <option value="">All Entities</option>
          <option value="reconciliation_run">Reconciliation Runs</option>
          <option value="exception">Exceptions</option>
          <option value="ingestion">Ingestion</option>
          <option value="event">Events</option>
          <option value="transaction">Transactions</option>
          <option value="settlement">Settlements</option>
        </select>
        <select
          value={filterActor}
          onChange={(e) => setFilterActor(e.target.value)}
          className="bg-fintrix-surface border border-fintrix-border rounded-lg px-3 py-2 text-sm text-fintrix-text focus:border-fintrix-primary outline-none cursor-pointer"
        >
          <option value="">All Actors</option>
          <option value="system">⚙️ System</option>
          <option value="ai_investigator">🤖 AI Investigator</option>
          <option value="human">👤 Human</option>
        </select>
        <button
          onClick={load}
          className="px-4 py-2 bg-fintrix-surface-2 border border-fintrix-border rounded-lg text-sm font-medium hover:bg-fintrix-surface-3 transition-colors cursor-pointer"
        >
          ↻ Refresh
        </button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="text-center py-16 text-fintrix-text-muted text-sm animate-pulse">
          Loading audit trail...
        </div>
      ) : logs.length === 0 ? (
        <div className="glass-card p-16 text-center">
          <span className="material-symbols-outlined text-fintrix-text-dimmed block mb-3" style={{ fontSize: "40px", opacity: 0.2 }}>history</span>
          <h3 className="text-sm font-semibold text-fintrix-text-muted mb-1">No audit entries yet</h3>
          <p className="text-xs text-fintrix-text-dimmed">Run the pipeline to generate audit trail entries</p>
        </div>
      ) : viewMode === "timeline" ? (
        /* Timeline View */
        <div className="glass-card p-6">
          <div className="relative">
            <div className="timeline-line" />
            {logs.slice(0, displayLimit).map((log) => (
              <TimelineEntry
                key={log.id}
                log={log}
                expanded={expandedId === log.id}
                onToggle={() => setExpandedId(expandedId === log.id ? null : log.id)}
              />
            ))}
          </div>
        </div>
      ) : (
        /* Table View */
        <div className="glass-card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-fintrix-border text-[11px] text-fintrix-text-muted uppercase tracking-wider">
                <th className="text-left px-4 py-3 font-medium">Time</th>
                <th className="text-left px-4 py-3 font-medium">Actor</th>
                <th className="text-left px-4 py-3 font-medium">Action</th>
                <th className="text-left px-4 py-3 font-medium">Entity</th>
                <th className="text-left px-4 py-3 font-medium">Details</th>
              </tr>
            </thead>
            <tbody>
              {logs.slice(0, displayLimit).map((log) => (
                <tr
                  key={log.id}
                  onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                  className="border-b border-fintrix-border/30 hover:bg-fintrix-surface-2/30 transition-colors cursor-pointer"
                >
                  <td className="px-4 py-3 text-[11px] text-fintrix-text-muted font-mono whitespace-nowrap" title={formatTimestamp(log.timestamp)}>
                    {timeAgo(log.timestamp)}
                  </td>
                  <td className="px-4 py-3">
                    <ActorBadge actor={log.actor} />
                  </td>
                  <td className="px-4 py-3">
                    <ActionBadge action={log.action} />
                  </td>
                  <td className="px-4 py-3 text-[11px] font-mono text-fintrix-text-muted">
                    <span className="text-fintrix-text">{log.entity_type}</span>
                    <span className="mx-1 opacity-30">:</span>
                    <span>{log.entity_id}</span>
                  </td>
                  <td className="px-4 py-3">
                    {expandedId === log.id ? (
                      <div className="animate-fade-in">
                        <StateDiffViewer oldState={log.old_state} newState={log.new_state} />
                      </div>
                    ) : (
                      <span className="text-[11px] text-fintrix-text-muted max-w-xs truncate block">
                        {log.new_state
                          ? Object.entries(log.new_state)
                              .slice(0, 3)
                              .map(([k, v]) => `${k}: ${typeof v === "object" ? "..." : v}`)
                              .join(" · ")
                          : "—"}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Load More */}
      {logs.length > displayLimit && (
        <div className="text-center pt-4">
          <button
            onClick={() => setDisplayLimit((prev) => prev + 25)}
            className="px-6 py-2.5 bg-fintrix-surface-2 border border-fintrix-border-subtle rounded-xl text-sm font-medium hover:bg-fintrix-surface-3 transition-colors cursor-pointer text-fintrix-text"
          >
            Load More (Showing {displayLimit} of {logs.length})
          </button>
        </div>
      )}
    </div>
  );
}
