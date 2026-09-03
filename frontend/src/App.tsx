import { useState, useEffect, useRef, useCallback } from "react";
import Dashboard from "./components/Dashboard";
import Exceptions from "./components/Exceptions";
import AuditTrail from "./components/AuditTrail";
import PipelineView from "./components/PipelineView";
import Analytics from "./components/Analytics";
import Settings from "./components/Settings";
import Login from "./components/Login";
import QAAgent from "./components/QAAgent";
import { api, type UserProfile } from "./api";

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: "dashboard", desc: "Overview & metrics" },
  { id: "pipeline", label: "Pipeline", icon: "account_tree", desc: "Run & monitor" },
  { id: "exceptions", label: "Exceptions", icon: "report_problem", desc: "Investigate & resolve" },
  { id: "qa", label: "Q&A Agent", icon: "smart_toy", desc: "Ask data questions" },
  { id: "analytics", label: "Analytics", icon: "analytics", desc: "Trends & ROI" },
  { id: "audit", label: "Audit Trail", icon: "verified_user", desc: "Immutable log" },
  { id: "settings", label: "Settings", icon: "settings", desc: "Config & keys" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");
  const [wsConnected, setWsConnected] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(api.isAuthenticated());
  const [user, setUser] = useState<UserProfile | null>(api.getStoredUser());
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [pageKey, setPageKey] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);

  // Check demo mode
  useEffect(() => {
    api.health().then((data) => {
      if (data.demo_mode) {
        setIsDemoMode(true);
        setIsAuthenticated(true);
        setUser({
          id: 1,
          email: "admin@fintrix.io",
          name: "Demo Admin",
          role: "admin",
          merchant_id: "demo_merchant",
          is_active: true,
          created_at: new Date().toISOString(),
        });
      }
    }).catch(console.error);
  }, []);

  // Listen for logout events
  useEffect(() => {
    const handleLogout = () => {
      if (isDemoMode) return; // Don't logout in demo mode
      setIsAuthenticated(false);
      setUser(null);
    };
    window.addEventListener("fintrix:logout", handleLogout);
    return () => window.removeEventListener("fintrix:logout", handleLogout);
  }, [isDemoMode]);

  // WebSocket connection (replaces SSE)
  const connectWS = useCallback(() => {
    if (!isAuthenticated) return;

    try {
      const ws = api.connectWebSocket();
      wsRef.current = ws;

      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        // Reconnect after 3 seconds
        setTimeout(connectWS, 3000);
      };
      ws.onerror = () => setWsConnected(false);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Handle ping/pong
          if (data.event === "ping") {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        } catch {}
      };
    } catch {
      // Fallback to SSE if WebSocket fails
      const es = new EventSource("/api/events/stream");
      es.addEventListener("connected", () => setWsConnected(true));
      es.addEventListener("ping", () => setWsConnected(true));
      es.onerror = () => setWsConnected(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    connectWS();
    return () => {
      wsRef.current?.close();
    };
  }, [connectWS]);

  const handleLogin = async () => {
    setIsAuthenticated(true);
    try {
      const profile = await api.getProfile();
      setUser(profile);
    } catch {
      setUser(api.getStoredUser());
    }
  };

  const handleLogout = () => {
    api.logout();
    setIsAuthenticated(false);
    setUser(null);
  };

  const handleTabChange = (tabId: TabId) => {
    if (tabId !== activeTab) {
      setActiveTab(tabId);
      setPageKey((k) => k + 1);
    }
  };

  // Show login if not authenticated
  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  const activeTabData = TABS.find((t) => t.id === activeTab)!;

  return (
    <div className="min-h-screen bg-fintrix-bg text-fintrix-text flex bg-grid-pattern">
      {/* ── Sidebar ──────────────────────────────────────────────── */}
      <aside className="w-[252px] shrink-0 bg-fintrix-surface/80 sidebar-glow flex flex-col backdrop-blur-sm">
        {/* Logo */}
        <div className="p-6 pb-5">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-fintrix-primary to-fintrix-accent flex items-center justify-center text-white text-lg font-black shadow-lg shadow-fintrix-primary/20">
              F
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight gradient-text">Fintrix</h1>
              <p className="text-[10px] text-fintrix-text-muted font-medium tracking-widest uppercase">
                AI Finance Controller
              </p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 space-y-0.5">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              id={`nav-${tab.id}`}
              onClick={() => handleTabChange(tab.id)}
              className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer group ${
                activeTab === tab.id
                  ? "bg-fintrix-primary/10 text-fintrix-primary"
                  : "text-fintrix-text-muted hover:bg-fintrix-surface-2/60 hover:text-fintrix-text"
              }`}
            >
              <span
                className={`material-symbols-outlined transition-all duration-200 ${
                  activeTab === tab.id ? "icon-filled" : "group-hover:text-fintrix-text"
                }`}
                style={{ fontSize: "19px" }}
              >
                {tab.icon}
              </span>
              <div className="text-left flex-1">
                <p className="leading-tight">{tab.label}</p>
                <p
                  className={`text-[10px] font-normal mt-0.5 transition-colors ${
                    activeTab === tab.id ? "text-fintrix-primary/60" : "text-fintrix-text-dimmed"
                  }`}
                >
                  {tab.desc}
                </p>
              </div>
              {activeTab === tab.id && (
                <div className="w-1.5 h-5 rounded-full bg-fintrix-primary shadow-lg shadow-fintrix-primary/50" />
              )}
            </button>
          ))}
        </nav>

        {/* User & Status */}
        <div className="p-4 mx-3 mb-3 rounded-xl bg-fintrix-surface-2/50 border border-fintrix-border-subtle">
          {/* User info */}
          {user && (
            <div className="flex items-center justify-between mb-3 pb-3 border-b border-fintrix-border-subtle">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-fintrix-primary/30 to-fintrix-accent/30 flex items-center justify-center text-[11px] font-bold text-fintrix-primary shrink-0">
                  {user.name.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] text-fintrix-text font-medium truncate">
                    {user.name} {isDemoMode && <span className="text-fintrix-primary ml-1">(Demo)</span>}
                  </p>
                  <p className="text-[10px] text-fintrix-text-dimmed truncate">{user.email}</p>
                </div>
              </div>
              {!isDemoMode && (
                <button
                  onClick={handleLogout}
                  className="text-fintrix-text-dimmed hover:text-red-400 transition-colors cursor-pointer shrink-0"
                  title="Logout"
                >
                  <span className="material-symbols-outlined icon-sm">logout</span>
                </button>
              )}
            </div>
          )}

          <div className="text-[11px] text-fintrix-text-dimmed">
            <p className="font-medium text-fintrix-text-muted">Razorpay AI Buildathon</p>
            <p className="mt-0.5">Track 4 · Finance Controller</p>
          </div>
        </div>
      </aside>

      {/* ── Main Content ─────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-[1440px] mx-auto p-6 lg:p-8">
          {/* Top Context Bar */}
          <div className="top-bar">
            <div className="top-bar-title">
              <span className="material-symbols-outlined icon-filled" style={{ fontSize: "22px" }}>
                {activeTabData.icon}
              </span>
              <div>
                <h2 className="text-lg font-semibold tracking-tight text-fintrix-text">{activeTabData.label}</h2>
                <div className="top-bar-breadcrumb">
                  <span>Fintrix</span>
                  <span className="separator">/</span>
                  <span className="text-fintrix-text-muted">{activeTabData.label}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-fintrix-surface-2/50 border border-fintrix-border-subtle">
                <span className={`status-dot ${wsConnected ? "status-dot-active" : "status-dot-danger"}`} />
                <span className="text-[11px] text-fintrix-text-muted">
                  {wsConnected ? "Live" : "Reconnecting"}
                </span>
              </div>
            </div>
          </div>

          {/* Page Content with Transition */}
          <div key={pageKey} className="page-enter">
            {activeTab === "dashboard" && <Dashboard />}
            {activeTab === "pipeline" && <PipelineView />}
            {activeTab === "exceptions" && <Exceptions />}
            {activeTab === "qa" && <QAAgent />}
            {activeTab === "analytics" && <Analytics />}
            {activeTab === "audit" && <AuditTrail />}
            {activeTab === "settings" && <Settings user={user} />}
          </div>
        </div>
      </main>
    </div>
  );
}
