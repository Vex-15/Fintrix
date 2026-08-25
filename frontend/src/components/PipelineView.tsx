import { useState, useEffect, useRef, useCallback } from "react";
import { api, type PipelineResult } from "../api";

function formatINR(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

// ── Stage Card ───────────────────────────────────────────────────────────────
function StageCard({
  stage,
  icon,
  status,
  stats,
  description,
}: {
  stage: string;
  icon: string;
  status: "idle" | "running" | "done" | "error";
  stats?: Record<string, string | number>;
  description: string;
}) {
  const styles = {
    idle: "border-fintrix-border bg-fintrix-surface text-fintrix-text-muted",
    running: "border-fintrix-primary/50 bg-fintrix-primary/8 text-fintrix-primary animate-glow-pulse",
    done: "border-fintrix-success/40 bg-fintrix-success/6 text-fintrix-success glow-success",
    error: "border-fintrix-danger/40 bg-fintrix-danger/6 text-fintrix-danger glow-danger",
  };

  const progressClasses = {
    idle: "",
    running: "animate-shimmer",
    done: "",
    error: "",
  };

  return (
    <div className={`glass-card p-5 transition-all duration-500 ${styles[status]} ${progressClasses[status]}`}>
      <div className="flex items-center gap-3 mb-3">
        <div className="text-2xl">{icon}</div>
        <div className="flex-1">
          <h4 className="text-sm font-bold">{stage}</h4>
          <p className="text-[10px] opacity-60">{description}</p>
        </div>
        {status === "done" && (
          <div className="w-7 h-7 rounded-full bg-fintrix-success/15 flex items-center justify-center">
            <span className="text-xs">✓</span>
          </div>
        )}
        {status === "running" && (
          <div className="w-7 h-7 rounded-full bg-fintrix-primary/15 flex items-center justify-center">
            <span className="text-xs animate-spin-slow" style={{ animationDuration: '2s', animation: 'spin-slow 2s linear infinite' }}>⟳</span>
          </div>
        )}
      </div>

      {stats && Object.keys(stats).length > 0 && (
        <div className="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-current/10">
          {Object.entries(stats).map(([key, val]) => (
            <div key={key}>
              <p className="text-[10px] opacity-50 uppercase tracking-wider">{key.replace(/_/g, " ")}</p>
              <p className="text-sm font-bold">{val}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Upload Zone ──────────────────────────────────────────────────────────────
function UploadZone({
  label,
  type,
  icon,
  onUpload,
  uploading,
  result,
}: {
  label: string;
  type: "transactions" | "settlements" | "bank-statements";
  icon: string;
  onUpload: (type: "transactions" | "settlements" | "bank-statements", file: File) => void;
  uploading: boolean;
  result: { records_stored: number; errors: string[] } | null;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) onUpload(type, file);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) onUpload(type, file);
  }

  return (
    <div
      className={`glass-card glass-card-hover p-5 transition-all duration-300 cursor-pointer ${
        dragOver ? "border-fintrix-primary/50 bg-fintrix-primary/5 scale-[1.02]" : ""
      }`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        onChange={handleChange}
        className="hidden"
      />

      <div className="text-center">
        <div className="text-2xl mb-2">{icon}</div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-[11px] text-fintrix-text-muted mt-1">
          {uploading ? "Uploading..." : "Drop CSV or click to browse"}
        </p>

        {result && (
          <div className="mt-3 pt-3 border-t border-fintrix-border-subtle">
            <p className="text-xs text-fintrix-success font-medium">
              ✓ {result.records_stored} records stored
            </p>
            {result.errors.length > 0 && (
              <p className="text-[10px] text-fintrix-warning mt-1">
                {result.errors.length} parse errors
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Pipeline View
// ═══════════════════════════════════════════════════════════════════════════════
export default function PipelineView() {
  const [dataStatus, setDataStatus] = useState<{ transactions: number; settlements: number; bank_statements: number } | null>(null);
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState<"idle" | "generating" | "reconciling" | "investigating" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [sseEvents, setSseEvents] = useState<{ time: string; message: string }[]>([]);
  const [uploadResults, setUploadResults] = useState<Record<string, { records_stored: number; errors: string[] }>>({});
  const [uploading, setUploading] = useState(false);
  const eventsRef = useRef<HTMLDivElement>(null);

  // Load status
  const loadStatus = useCallback(async () => {
    try {
      const status = await api.ingestionStatus();
      setDataStatus(status);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  // SSE listener
  useEffect(() => {
    const es = new EventSource("/api/events/stream");

    const addEvent = (msg: string) => {
      const time = new Date().toLocaleTimeString();
      setSseEvents((prev) => [...prev.slice(-50), { time, message: msg }]);
    };

    es.addEventListener("pipeline.step", (e) => {
      const data = JSON.parse(e.data);
      addEvent(`${data.step}: ${data.status}${data.matched ? ` (${data.matched} matched)` : ""}`);
      if (data.step === "investigation" && data.status === "started") setStage("investigating");
    });
    es.addEventListener("pipeline.completed", (e) => {
      const data = JSON.parse(e.data);
      addEvent(`✓ Pipeline complete — ${data.matched} matched, ${data.auto_resolved} auto-resolved, ${data.escalated} escalated`);
    });
    es.addEventListener("investigation.completed", (e) => {
      const data = JSON.parse(e.data);
      addEvent(`🧠 #${data.exception_id}: ${data.action} (${Math.round(data.confidence * 100)}% conf)`);
    });

    return () => es.close();
  }, []);

  // Auto-scroll events
  useEffect(() => {
    if (eventsRef.current) {
      eventsRef.current.scrollTop = eventsRef.current.scrollHeight;
    }
  }, [sseEvents]);

  // Upload handler
  async function handleUpload(type: "transactions" | "settlements" | "bank-statements", file: File) {
    setUploading(true);
    try {
      const result = await api.uploadCSV(type, file);
      setUploadResults((prev) => ({ ...prev, [type]: result }));
      await loadStatus();
    } catch {
      // ignore
    } finally {
      setUploading(false);
    }
  }

  // Generate + Run
  async function handleFullPipeline() {
    setLoading(true);
    setError(null);
    setPipelineResult(null);
    setSseEvents([]);

    try {
      // Generate
      setStage("generating");
      await api.generateData();
      await loadStatus();

      // Run pipeline
      setStage("reconciling");
      const result = await api.runFullPipeline();
      setPipelineResult(result);
      setStage("done");
      await loadStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pipeline failed");
      setStage("idle");
    } finally {
      setLoading(false);
    }
  }

  // Run only (data already loaded)
  async function handleRunOnly() {
    setLoading(true);
    setError(null);
    setPipelineResult(null);
    setSseEvents([]);

    try {
      setStage("reconciling");
      const result = await api.runFullPipeline();
      setPipelineResult(result);
      setStage("done");
      await loadStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pipeline failed");
      setStage("idle");
    } finally {
      setLoading(false);
    }
  }

  const hasData = dataStatus && dataStatus.transactions > 0;

  return (
    <div className="space-y-8 stagger-children">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Pipeline Execution</h2>
          <p className="text-sm text-fintrix-text-muted mt-1.5">
            Ingest data → Reconcile → AI Investigation → Resolve/Escalate
          </p>
        </div>
        <div className="flex gap-3">
          {!hasData ? (
            <button
              onClick={handleFullPipeline}
              disabled={loading}
              className="btn-gradient disabled:opacity-40"
              id="btn-demo"
            >
              <span>{loading ? "Running..." : "⚡ One-Click Demo"}</span>
            </button>
          ) : (
            <>
              <button
                onClick={handleFullPipeline}
                disabled={loading}
                className="px-4 py-2.5 bg-fintrix-surface-2 border border-fintrix-border rounded-xl text-sm font-medium hover:bg-fintrix-surface-3 transition-colors cursor-pointer disabled:opacity-40"
              >
                <span>{loading ? "..." : "🔄 Reload & Run"}</span>
              </button>
              <button
                onClick={handleRunOnly}
                disabled={loading}
                className="btn-gradient disabled:opacity-40"
                id="btn-run"
              >
                <span>{loading ? "Running Pipeline..." : "▶ Run Pipeline"}</span>
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="glass-card p-4 border-fintrix-danger/30 bg-fintrix-danger/5">
          <p className="text-sm text-fintrix-danger">{error}</p>
        </div>
      )}

      {/* Upload Zone */}
      <div>
        <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-4">
          Data Sources {hasData && <span className="text-fintrix-success ml-2">● Loaded</span>}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <UploadZone
            label="Transactions"
            type="transactions"
            icon="💳"
            onUpload={handleUpload}
            uploading={uploading}
            result={uploadResults["transactions"] || null}
          />
          <UploadZone
            label="Settlements"
            type="settlements"
            icon="💰"
            onUpload={handleUpload}
            uploading={uploading}
            result={uploadResults["settlements"] || null}
          />
          <UploadZone
            label="Bank Statements"
            type="bank-statements"
            icon="🏦"
            onUpload={handleUpload}
            uploading={uploading}
            result={uploadResults["bank-statements"] || null}
          />
        </div>
        {hasData && dataStatus && (
          <div className="flex gap-6 mt-3 text-xs text-fintrix-text-muted">
            <span>{dataStatus.transactions} transactions</span>
            <span>{dataStatus.settlements} settlements</span>
            <span>{dataStatus.bank_statements} bank entries</span>
          </div>
        )}
      </div>

      {/* Pipeline Stages */}
      <div>
        <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-4">
          Pipeline Stages
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StageCard
            stage="Ingest"
            icon="📥"
            description="Load financial records"
            status={stage === "generating" ? "running" : stage !== "idle" ? "done" : "idle"}
            stats={hasData && dataStatus ? { records: dataStatus.transactions + dataStatus.settlements + dataStatus.bank_statements, sources: 3 } : undefined}
          />
          <StageCard
            stage="Reconcile"
            icon="⚖️"
            description="6-step deterministic matching"
            status={stage === "reconciling" ? "running" : pipelineResult ? "done" : "idle"}
            stats={pipelineResult ? {
              matched: pipelineResult.reconciliation.matched,
              exceptions: pipelineResult.reconciliation.exceptions,
              duration: `${pipelineResult.reconciliation.duration_ms}ms`,
            } : undefined}
          />
          <StageCard
            stage="Investigate"
            icon="🧠"
            description="AI-powered root-cause analysis"
            status={stage === "investigating" ? "running" : pipelineResult ? "done" : "idle"}
            stats={pipelineResult ? {
              investigated: pipelineResult.investigation.total_investigated,
              "auto resolved": pipelineResult.investigation.auto_resolved,
            } : undefined}
          />
          <StageCard
            stage="Resolve"
            icon="✅"
            description="Risk-aware auto-resolution"
            status={stage === "done" ? "done" : "idle"}
            stats={pipelineResult ? {
              resolved: pipelineResult.investigation.auto_resolved,
              escalated: pipelineResult.investigation.escalated,
              "needs review": pipelineResult.investigation.human_review || 0,
            } : undefined}
          />
        </div>
      </div>

      {/* Results Summary */}
      {pipelineResult && (
        <div className="glass-card p-6">
          <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-4">
            Pipeline Results Summary
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <div>
              <p className="text-[10px] text-fintrix-text-muted uppercase tracking-wider mb-1">Total Records</p>
              <p className="text-xl font-bold">{pipelineResult.reconciliation.total_records}</p>
            </div>
            <div>
              <p className="text-[10px] text-fintrix-text-muted uppercase tracking-wider mb-1">Match Rate</p>
              <p className="text-xl font-bold text-fintrix-success">
                {((pipelineResult.reconciliation.matched / Math.max(pipelineResult.reconciliation.total_records, 1)) * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <p className="text-[10px] text-fintrix-text-muted uppercase tracking-wider mb-1">Exceptions</p>
              <p className="text-xl font-bold text-fintrix-warning">{pipelineResult.reconciliation.exceptions}</p>
            </div>
            <div>
              <p className="text-[10px] text-fintrix-text-muted uppercase tracking-wider mb-1">Auto-Resolved</p>
              <p className="text-xl font-bold text-fintrix-accent">{pipelineResult.investigation.auto_resolved}</p>
            </div>
            <div>
              <p className="text-[10px] text-fintrix-text-muted uppercase tracking-wider mb-1">Escalated</p>
              <p className="text-xl font-bold text-fintrix-danger">{pipelineResult.investigation.escalated}</p>
            </div>
            <div>
              <p className="text-[10px] text-fintrix-text-muted uppercase tracking-wider mb-1">Throughput</p>
              <p className="text-xl font-bold">
                {Math.round(pipelineResult.reconciliation.total_records / (pipelineResult.reconciliation.duration_ms / 1000))}
                <span className="text-xs text-fintrix-text-muted ml-1">rec/s</span>
              </p>
            </div>
          </div>

          {/* Exception type breakdown */}
          {pipelineResult.summary.exception_types && (
            <div className="mt-5 pt-5 border-t border-fintrix-border">
              <p className="text-[10px] text-fintrix-text-muted uppercase tracking-wider mb-3">Exception Types Detected</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(pipelineResult.summary.exception_types as Record<string, number>).map(([type, count]) => (
                  <span
                    key={type}
                    className="px-3 py-1.5 rounded-lg bg-fintrix-surface-2/50 border border-fintrix-border-subtle text-xs font-medium"
                  >
                    <span className="text-fintrix-text-muted capitalize">{type.replace(/_/g, " ")}</span>
                    <span className="ml-2 text-fintrix-text font-bold">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Live Event Feed */}
      <div className="glass-card p-6">
        <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-4">
          Live Event Stream
          {sseEvents.length > 0 && (
            <span className="ml-2 status-dot status-dot-active inline-block" />
          )}
        </h3>
        <div
          ref={eventsRef}
          className="space-y-1 max-h-64 overflow-y-auto font-mono text-[12px]"
        >
          {sseEvents.length > 0 ? (
            sseEvents.map((evt, i) => (
              <div
                key={i}
                className="flex gap-3 py-1 text-fintrix-text-muted animate-fade-in"
              >
                <span className="text-fintrix-text-dimmed shrink-0">{evt.time}</span>
                <span className="text-fintrix-accent shrink-0">›</span>
                <span>{evt.message}</span>
              </div>
            ))
          ) : (
            <p className="text-sm text-fintrix-text-dimmed py-4 text-center">
              {loading ? "Waiting for pipeline events..." : "Run the pipeline to see live events"}
            </p>
          )}
        </div>
      </div>

      {/* Guardrails Info */}
      <div className="glass-card p-6">
        <h3 className="text-xs font-semibold text-fintrix-text-muted uppercase tracking-wider mb-4">
          AI Guardrails & Safety
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-xs font-semibold text-fintrix-text">&gt;85% Confidence</span>
            </div>
            <p className="text-[11px] text-fintrix-text-muted pl-4">
              Auto-resolve if amount ≤ ₹10,000
            </p>
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-amber-500" />
              <span className="text-xs font-semibold text-fintrix-text">65-85% Confidence</span>
            </div>
            <p className="text-[11px] text-fintrix-text-muted pl-4">
              Requires human approval before resolution
            </p>
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-red-500" />
              <span className="text-xs font-semibold text-fintrix-text">&lt;65% or LLM Down</span>
            </div>
            <p className="text-[11px] text-fintrix-text-muted pl-4">
              Always escalated — system never guesses
            </p>
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-fintrix-border-subtle">
          <p className="text-[11px] text-fintrix-text-dimmed">
            <span className="text-fintrix-primary font-medium">Failure-safe:</span> If the LLM is unavailable, reconciliation still completes deterministically.
            Unresolved exceptions are escalated for manual review — the system never fabricates resolutions.
          </p>
        </div>
      </div>
    </div>
  );
}
