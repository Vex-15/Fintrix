/**
 * Fintrix API client — all backend calls in one place.
 * Enhanced with: auth, dashboard stats, deep investigation, bulk actions,
 * audit timeline, analytics, export, API keys, notes, WebSocket.
 */

const API_BASE = "/api";

// ═══════════════════════════════════════════════════════════════════════════
// Auth Token Management
// ═══════════════════════════════════════════════════════════════════════════

function getToken(): string | null {
  return localStorage.getItem("fintrix_access_token");
}

function getRefreshToken(): string | null {
  return localStorage.getItem("fintrix_refresh_token");
}

function setTokens(access: string, refresh: string) {
  localStorage.setItem("fintrix_access_token", access);
  localStorage.setItem("fintrix_refresh_token", refresh);
}

function clearTokens() {
  localStorage.removeItem("fintrix_access_token");
  localStorage.removeItem("fintrix_refresh_token");
  localStorage.removeItem("fintrix_user");
}

function getStoredUser(): UserProfile | null {
  const u = localStorage.getItem("fintrix_user");
  return u ? JSON.parse(u) : null;
}

function setStoredUser(user: UserProfile) {
  localStorage.setItem("fintrix_user", JSON.stringify(user));
}

// ═══════════════════════════════════════════════════════════════════════════
// HTTP Client
// ═══════════════════════════════════════════════════════════════════════════

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };

  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  // Auto-refresh on 401
  if (res.status === 401 && getRefreshToken()) {
    const refreshed = await _tryRefreshToken();
    if (refreshed) {
      headers["Authorization"] = `Bearer ${getToken()}`;
      const retryRes = await fetch(`${API_BASE}${path}`, { ...options, headers });
      if (retryRes.ok) return retryRes.json();
    }
    // Refresh failed — clear tokens
    clearTokens();
    window.dispatchEvent(new Event("fintrix:logout"));
    throw new Error("Session expired. Please login again.");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function _tryRefreshToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: getRefreshToken() }),
    });
    if (res.ok) {
      const data: TokenResponse = await res.json();
      setTokens(data.access_token, data.refresh_token);
      setStoredUser(data.user);
      return true;
    }
  } catch {}
  return false;
}

// ═══════════════════════════════════════════════════════════════════════════
// API Methods
// ═══════════════════════════════════════════════════════════════════════════

export const api = {
  // ── Auth ──────────────────────────────────────────────────────────────
  register: async (email: string, password: string, name: string) => {
    const data = await request<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    });
    setTokens(data.access_token, data.refresh_token);
    setStoredUser(data.user);
    return data;
  },

  login: async (email: string, password: string) => {
    const data = await request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setTokens(data.access_token, data.refresh_token);
    setStoredUser(data.user);
    return data;
  },

  logout: () => {
    clearTokens();
    window.dispatchEvent(new Event("fintrix:logout"));
  },

  health: async () => {
    const res = await fetch(`${API_BASE.replace('/api', '')}/health`);
    return res.json();
  },
  
  getProfile: () => request<UserProfile>("/auth/me"),
  updateProfile: (data: { name?: string; password?: string }) =>
    request<UserProfile>("/auth/me", { method: "PUT", body: JSON.stringify(data) }),

  getStoredUser,
  isAuthenticated: () => !!getToken(),

  // ── Status ────────────────────────────────────────────────────────────
  health: () => fetch("/health").then((r) => r.json()),
  ingestionStatus: () => request<{ transactions: number; settlements: number; bank_statements: number }>("/ingest/status"),

  // ── Synthetic data ────────────────────────────────────────────────────
  generateData: () => request<{ message: string; counts: Record<string, number>; ground_truth: GroundTruth }>("/ingest/generate-synthetic-data", { method: "POST" }),

  // ── Upload CSV ────────────────────────────────────────────────────────
  uploadCSV: async (type: "transactions" | "settlements" | "bank-statements", file: File) => {
    const form = new FormData();
    form.append("file", file);
    const headers: Record<string, string> = {};
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}/ingest/csv/${type}`, { method: "POST", body: form, headers });
    return res.json();
  },

  // ── Reconciliation ────────────────────────────────────────────────────
  runReconciliation: () => request<ReconciliationRun>("/reconciliation/run", { method: "POST" }),
  listRuns: () => request<ReconciliationRun[]>("/reconciliation/runs"),
  getRun: (id: number) => request<ReconciliationRun>(`/reconciliation/runs/${id}`),
  getRunResults: (id: number) => request<ReconciliationResult[]>(`/reconciliation/runs/${id}/results`),
  getMetrics: () => request<ReconciliationMetrics>("/reconciliation/metrics"),
  getDashboardStats: () => request<DashboardStats>("/reconciliation/dashboard-stats"),

  // ── Exceptions ────────────────────────────────────────────────────────
  listExceptions: (params?: { status?: string; severity?: string; type?: string; run_id?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.severity) qs.set("severity", params.severity);
    if (params?.type) qs.set("type", params.type);
    if (params?.run_id) qs.set("run_id", String(params.run_id));
    return request<ExceptionItem[]>(`/exceptions/?${qs}`);
  },
  getException: (id: number) => request<ExceptionItem>(`/exceptions/${id}`),
  getDeepInvestigation: (id: number) => request<DeepInvestigation>(`/exceptions/${id}/deep-investigation`),
  exceptionSummary: (runId?: number) => {
    const qs = runId ? `?run_id=${runId}` : "";
    return request<ExceptionSummary>(`/exceptions/summary${qs}`);
  },
  actOnException: (id: number, action: string, reason?: string) =>
    request(`/exceptions/${id}/action`, {
      method: "POST",
      body: JSON.stringify({ action, reason }),
    }),
  bulkAction: (exceptionIds: number[], action: string, reason?: string) =>
    request("/exceptions/bulk-action", {
      method: "POST",
      body: JSON.stringify({ exception_ids: exceptionIds, action, reason }),
    }),
  addFeedback: (id: number, feedback: "helpful" | "unhelpful") =>
    request(`/exceptions/${id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),

  // ── Exception Notes ───────────────────────────────────────────────────
  listNotes: (exceptionId: number) => request<ExceptionNote[]>(`/exceptions/${exceptionId}/notes`),
  addNote: (exceptionId: number, content: string) =>
    request<ExceptionNote>(`/exceptions/${exceptionId}/notes`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  // ── Pipeline ──────────────────────────────────────────────────────────
  runFullPipeline: () => request<PipelineResult>("/events/run-full-pipeline", { method: "POST" }),
  investigateAll: (runId: number) => request(`/events/investigate-all?run_id=${runId}`, { method: "POST" }),

  // ── Audit ─────────────────────────────────────────────────────────────
  listAuditLogs: (params?: { entity_type?: string; actor?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.entity_type) qs.set("entity_type", params.entity_type);
    if (params?.actor) qs.set("actor", params.actor);
    if (params?.limit) qs.set("limit", String(params.limit));
    return request<AuditLogEntry[]>(`/audit/?${qs}`);
  },
  getEntityTimeline: (entityType: string, entityId: string) =>
    request<EntityTimeline>(`/audit/timeline/${entityType}/${entityId}`),
  getAuditStats: () => request<AuditStats>("/audit/stats"),

  // ── Analytics ─────────────────────────────────────────────────────────
  getTrends: (days?: number) => request<TrendData>(`/analytics/trends${days ? `?days=${days}` : ""}`),
  getSLA: (days?: number) => request<SLAData>(`/analytics/sla${days ? `?days=${days}` : ""}`),
  getROI: () => request<ROIData>("/analytics/roi"),

  // ── API Keys ──────────────────────────────────────────────────────────
  listAPIKeys: () => request<APIKeyInfo[]>("/api-keys/"),
  createAPIKey: (name: string, scopes?: Record<string, boolean>) =>
    request<APIKeyCreated>("/api-keys/", {
      method: "POST",
      body: JSON.stringify({ name, scopes }),
    }),
  revokeAPIKey: (id: number) => request(`/api-keys/${id}`, { method: "DELETE" }),

  // ── Export ────────────────────────────────────────────────────────────
  exportTransactions: () => {
    const token = getToken();
    window.open(`${API_BASE}/export/transactions${token ? `?token=${token}` : ""}`, "_blank");
  },
  exportExceptions: () => {
    const token = getToken();
    window.open(`${API_BASE}/export/exceptions${token ? `?token=${token}` : ""}`, "_blank");
  },
  exportAuditTrail: () => {
    const token = getToken();
    window.open(`${API_BASE}/export/audit-trail${token ? `?token=${token}` : ""}`, "_blank");
  },

  // ── Scheduler ─────────────────────────────────────────────────────────
  getSchedulerStatus: () => request<SchedulerStatus>("/scheduler/status"),

  // ── WebSocket ─────────────────────────────────────────────────────────
  connectWebSocket: (): WebSocket => {
    const token = getToken();
    const wsUrl = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}${API_BASE}/ws${token ? `?token=${token}` : ""}`;
    return new WebSocket(wsUrl);
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════

export interface UserProfile {
  id: number;
  email: string;
  name: string;
  role: string;
  merchant_id: string | null;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserProfile;
}

export interface ReconciliationRun {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  trigger_type: string;
  total_records: number;
  matched: number;
  mismatched: number;
  unmatched: number;
  exceptions_count: number;
  duration_ms: number | null;
  summary: Record<string, unknown>;
}

export interface ReconciliationResult {
  id: number;
  run_id: number;
  transaction_id: string | null;
  settlement_id: string | null;
  match_type: string;
  match_status: string;
  match_score: number | null;
  expected_amount: number | null;
  actual_amount: number | null;
  difference: number;
  match_details: Record<string, unknown>;
}

export interface ReconciliationMetrics {
  total_records: number;
  matched: number;
  mismatched: number;
  unmatched: number;
  exceptions_total: number;
  auto_resolved: number;
  escalated: number;
  unresolved: number;
  match_rate: number;
  throughput_records_per_sec: number;
  avg_ai_latency_ms: number | null;
  audit_completeness: number;
}

export interface ExceptionItem {
  id: number;
  run_id: number | null;
  type: string;
  severity: string;
  status: string;
  amount_at_risk: number;
  context: Record<string, unknown>;
  created_at: string;
  resolved_at: string | null;
  investigation: Investigation | null;
}

export interface Investigation {
  id: number;
  exception_id: number;
  root_cause: string;
  evidence: { points: string[] };
  confidence: number;
  recommended_action: string;
  explanation: string;
  resolution_type: string | null;
  resolved_by: string | null;
  model_used: string | null;
  prompt_tokens: number | null;
  response_tokens: number | null;
  latency_ms: number | null;
  chain_of_thought: Record<string, unknown> | null;
  created_at: string;
}

export interface ExceptionSummary {
  by_type: Record<string, number>;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
  total: number;
}

export interface ExceptionNote {
  id: number;
  exception_id: number;
  user_id: number | null;
  content: string;
  created_at: string;
}

export interface AuditLogEntry {
  id: number;
  timestamp: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor: string;
  old_state: Record<string, unknown> | null;
  new_state: Record<string, unknown> | null;
}

export interface GroundTruth {
  total_transactions: number;
  total_settlements: number;
  total_bank_statements: number;
  expected_matched: number;
  planted_exceptions: { transaction_id: string; type: string; detail: string }[];
  exception_counts: Record<string, number>;
}

export interface PipelineResult {
  run_id: number;
  reconciliation: {
    total_records: number;
    matched: number;
    mismatched: number;
    unmatched: number;
    exceptions: number;
    duration_ms: number;
  };
  investigation: {
    total_investigated: number;
    auto_resolved: number;
    escalated: number;
    human_review: number;
  };
  summary: Record<string, unknown>;
}

export interface DashboardStats {
  data_sources: { transactions: number; settlements: number; bank_statements: number };
  run_history: {
    id: number;
    started_at: string;
    completed_at: string | null;
    status: string;
    total_records: number;
    matched: number;
    mismatched: number;
    unmatched: number;
    exceptions_count: number;
    duration_ms: number | null;
  }[];
  exceptions: {
    total: number;
    by_status: Record<string, number>;
    by_type: Record<string, number>;
    by_severity: Record<string, number>;
    pending: number;
    resolved: number;
    escalated: number;
    auto_resolved: number;
    manual_resolved: number;
  };
  financial: { total_at_risk: number; resolved_at_risk: number; pending_at_risk: number };
  recent_exceptions: {
    id: number;
    type: string;
    severity: string;
    status: string;
    amount_at_risk: number;
    created_at: string;
    investigation: { confidence: number; recommended_action: string; root_cause: string } | null;
  }[];
}

export interface DeepInvestigation {
  exception: {
    id: number;
    run_id: number | null;
    type: string;
    severity: string;
    status: string;
    amount_at_risk: number;
    context: Record<string, unknown>;
    created_at: string;
    resolved_at: string | null;
  };
  transaction_records: {
    id: string;
    type: string;
    order_id: string | null;
    amount: number;
    currency: string;
    status: string;
    fee: number;
    tax: number;
    settlement_id: string | null;
    method: string | null;
    description: string | null;
    captured_at: string | null;
    created_at: string | null;
    source: string;
  }[];
  settlement_record: {
    id: string;
    amount: number;
    fees: number;
    tax: number;
    utr: string | null;
    status: string;
    created_at: string | null;
  } | null;
  bank_record: {
    id: number;
    bank_account: string;
    entry_date: string | null;
    description: string | null;
    reference: string | null;
    credit: number;
    debit: number;
    balance: number | null;
  } | null;
  reconciliation_result: {
    match_type: string;
    match_status: string;
    match_score: number | null;
    expected_amount: number | null;
    actual_amount: number | null;
    difference: number;
    match_details: Record<string, unknown>;
  } | null;
  investigation: {
    id: number;
    root_cause: string;
    evidence: { points: string[] };
    confidence: number;
    recommended_action: string;
    explanation: string;
    resolution_type: string | null;
    resolved_by: string | null;
    model_used: string | null;
    prompt_tokens: number | null;
    response_tokens: number | null;
    latency_ms: number | null;
    chain_of_thought: Record<string, unknown> | null;
    agent_decision_trace?: Record<string, unknown> | null;
    user_feedback?: string | null;
    created_at: string | null;
  } | null;
  comparison: {
    transaction_side: { gross_amount: number; fees: number; tax: number; refunds: number; net_amount: number; record_count: number };
    settlement_side: { amount: number | null; fees: number | null; tax: number | null; utr: string | null } | null;
    bank_side: { credit: number | null; reference: string | null; entry_date: string | null } | null;
    discrepancy: { type: string; amount_at_risk: number; severity: string };
  } | null;
  timeline: {
    id: number;
    timestamp: string;
    action: string;
    actor: string;
    old_state: Record<string, unknown> | null;
    new_state: Record<string, unknown> | null;
  }[];
  notes: { id: number; user_id: number | null; content: string; created_at: string }[];
}

export interface EntityTimeline {
  entity_type: string;
  entity_id: string;
  total_entries: number;
  timeline: {
    id: number;
    timestamp: string;
    action: string;
    actor: string;
    old_state: Record<string, unknown> | null;
    new_state: Record<string, unknown> | null;
    metadata: Record<string, unknown> | null;
    diff: Record<string, { before: unknown; after: unknown }> | null;
  }[];
}

export interface AuditStats {
  total: number;
  by_actor: Record<string, number>;
  by_action: Record<string, number>;
  by_entity_type: Record<string, number>;
}

// Analytics types
export interface TrendData {
  period_days: number;
  run_trends: {
    date: string;
    run_id: number;
    total_records: number;
    matched: number;
    exceptions: number;
    accuracy: number;
    duration_ms: number;
  }[];
  exception_trends: {
    date: string;
    total: number;
    resolved: number;
    escalated: number;
    total_risk_paise: number;
  }[];
  summary: {
    total_runs: number;
    avg_accuracy: number;
    total_exceptions: number;
    total_resolved: number;
  };
}

export interface SLAData {
  period_days: number;
  investigation_latency_ms: PercentileData;
  time_to_resolve_seconds: PercentileData;
  reconciliation_duration_ms: PercentileData;
  throughput: { total_runs: number; total_records_processed: number; avg_records_per_run: number };
}

export interface PercentileData {
  p50: number | null;
  p95: number | null;
  p99: number | null;
  avg: number | null;
  count: number;
}

export interface ROIData {
  total_records_processed: number;
  total_exceptions: number;
  auto_resolved: number;
  auto_resolve_rate: number;
  time_savings: { reconciliation_hours: number; investigation_hours: number; total_hours_saved: number };
  cost_savings: { hourly_rate: number; total_saved_rupees: number };
  accuracy: { avg_ai_latency_ms: number | null; manual_time_per_exception_min: number; speedup_factor: number | null };
  amount_at_risk_resolved_paise: number;
  amount_at_risk_resolved_rupees: number;
}

export interface APIKeyInfo {
  id: number;
  key_prefix: string;
  name: string;
  scopes: Record<string, boolean>;
  is_active: boolean;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface APIKeyCreated {
  id: number;
  raw_key: string;
  key_prefix: string;
  name: string;
  scopes: Record<string, boolean>;
  created_at: string;
}

export interface SchedulerStatus {
  status: string;
  jobs: { id: string; name: string; next_run: string | null; trigger: string }[];
}
