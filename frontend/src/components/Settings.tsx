import { useState, useEffect } from "react";
import { api, type APIKeyInfo, type APIKeyCreated, type SchedulerStatus, type UserProfile } from "../api";

interface SettingsProps {
  user: UserProfile | null;
}

export default function Settings({ user }: SettingsProps) {
  const [activeSection, setActiveSection] = useState("api-keys");
  const [apiKeys, setApiKeys] = useState<APIKeyInfo[]>([]);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [newKeyName, setNewKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState<APIKeyCreated | null>(null);
  const [loading, setLoading] = useState(false);
  const [profileName, setProfileName] = useState(user?.name || "");
  const [profilePassword, setProfilePassword] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  
  // Determinism Test State
  const [determinismResult, setDeterminismResult] = useState<any>(null);
  const [runningDeterminism, setRunningDeterminism] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [keys, sched] = await Promise.all([
        api.listAPIKeys().catch(() => []),
        api.getSchedulerStatus().catch(() => null),
      ]);
      setApiKeys(keys);
      setScheduler(sched);
    } catch {}
  };

  const createKey = async () => {
    if (!newKeyName.trim()) return;
    setLoading(true);
    try {
      const key = await api.createAPIKey(newKeyName);
      setCreatedKey(key);
      setNewKeyName("");
      loadData();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  };

  const revokeKey = async (id: number) => {
    if (!confirm("Revoke this API key? This cannot be undone.")) return;
    try {
      await api.revokeAPIKey(id);
      loadData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const updateProfile = async () => {
    try {
      const data: { name?: string; password?: string } = {};
      if (profileName && profileName !== user?.name) data.name = profileName;
      if (profilePassword) data.password = profilePassword;
      if (Object.keys(data).length === 0) return;

      await api.updateProfile(data);
      setProfileMessage("Profile updated successfully!");
      setProfilePassword("");
      setTimeout(() => setProfileMessage(""), 3000);
    } catch (err: any) {
      setProfileMessage(`Error: ${err.message}`);
    }
  };

  const sections = [
    { id: "api-keys", label: "API Keys", icon: "key" },
    { id: "profile", label: "Profile", icon: "person" },
    { id: "scheduler", label: "Scheduler", icon: "schedule" },
    { id: "razorpay", label: "Razorpay", icon: "credit_card" },
    { id: "export", label: "Export Data", icon: "download" },
    { id: "diagnostics", label: "Diagnostics", icon: "build" },
  ];

  return (
    <div className="space-y-6 animate-fadeIn">
      <div>
        <h2 className="text-2xl font-bold gradient-text">Settings</h2>
        <p className="text-fintrix-text-muted text-sm mt-1">Configuration, API keys & integrations</p>
      </div>

      <div className="flex gap-6">
        {/* Sidebar */}
        <div className="w-48 shrink-0 space-y-1">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveSection(s.id)}
              className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm transition-all cursor-pointer ${
                activeSection === s.id
                  ? "bg-fintrix-primary/12 text-fintrix-primary"
                  : "text-fintrix-text-muted hover:bg-fintrix-surface-2 hover:text-fintrix-text"
              }`}
            >
              <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>{s.icon}</span>
              {s.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* API Keys */}
          {activeSection === "api-keys" && (
            <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-fintrix-text mb-1">API Keys</h3>
                <p className="text-sm text-fintrix-text-muted">Manage programmatic access to the Fintrix API.</p>
              </div>

              {/* Create */}
              <div className="flex gap-3">
                <input
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="Key name (e.g., Production App)"
                  className="flex-1 px-4 py-2.5 rounded-xl bg-fintrix-surface-2/70 border border-fintrix-border-subtle text-fintrix-text placeholder-fintrix-text-dimmed focus:outline-none focus:border-fintrix-primary/50 text-sm"
                />
                <button
                  onClick={createKey}
                  disabled={loading || !newKeyName.trim()}
                  className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-fintrix-primary to-fintrix-accent text-white text-sm font-medium disabled:opacity-50 cursor-pointer hover:shadow-lg hover:shadow-fintrix-primary/25 transition-all"
                >
                  Generate Key
                </button>
              </div>

              {/* Show created key */}
              {createdKey && (
                <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
                  <p className="text-sm text-emerald-400 font-medium mb-2">⚠ Copy this key now. It won't be shown again!</p>
                  <code className="block p-3 rounded-lg bg-fintrix-surface-2/80 text-sm font-mono text-fintrix-text break-all select-all">
                    {createdKey.raw_key}
                  </code>
                  <button
                    onClick={() => { navigator.clipboard.writeText(createdKey.raw_key); setCreatedKey(null); }}
                    className="mt-2 px-3 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 text-xs font-medium cursor-pointer hover:bg-emerald-500/30 transition-all"
                  >
                    Copy & Dismiss
                  </button>
                </div>
              )}

              {/* Key list */}
              <div className="space-y-2">
                {apiKeys.map((key) => (
                  <div key={key.id} className="flex items-center justify-between p-3 rounded-xl bg-fintrix-surface-2/30 border border-fintrix-border-subtle">
                    <div>
                      <p className="text-sm text-fintrix-text font-medium">{key.name}</p>
                      <p className="text-xs text-fintrix-text-dimmed font-mono">{key.key_prefix}••••••••</p>
                    </div>
                    <div className="flex items-center gap-3">
                      {key.last_used_at && (
                        <span className="text-[10px] text-fintrix-text-dimmed">
                          Last used: {new Date(key.last_used_at).toLocaleDateString()}
                        </span>
                      )}
                      <button
                        onClick={() => revokeKey(key.id)}
                        className="px-3 py-1.5 rounded-lg bg-red-500/10 text-red-400 text-xs font-medium cursor-pointer hover:bg-red-500/20 transition-all"
                      >
                        Revoke
                      </button>
                    </div>
                  </div>
                ))}
                {apiKeys.length === 0 && (
                  <p className="text-sm text-fintrix-text-dimmed text-center py-4">No API keys yet.</p>
                )}
              </div>
            </div>
          )}

          {/* Profile */}
          {activeSection === "profile" && (
            <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle space-y-5">
              <div>
                <h3 className="text-lg font-semibold text-fintrix-text mb-1">Profile</h3>
                <p className="text-sm text-fintrix-text-muted">Manage your account settings.</p>
              </div>

              <div>
                <label className="block text-xs font-medium text-fintrix-text-muted mb-1.5 uppercase tracking-wider">Email</label>
                <input value={user?.email || ""} disabled className="w-full px-4 py-3 rounded-xl bg-fintrix-surface-2/50 border border-fintrix-border-subtle text-fintrix-text-dimmed text-sm cursor-not-allowed" />
              </div>

              <div>
                <label className="block text-xs font-medium text-fintrix-text-muted mb-1.5 uppercase tracking-wider">Role</label>
                <div className={`inline-flex px-3 py-1.5 rounded-lg text-xs font-medium ${
                  user?.role === "admin" ? "bg-violet-500/15 text-violet-400" :
                  user?.role === "operator" ? "bg-blue-500/15 text-blue-400" :
                  "bg-gray-500/15 text-gray-400"
                }`}>
                  {user?.role?.toUpperCase()}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-fintrix-text-muted mb-1.5 uppercase tracking-wider">Name</label>
                <input value={profileName} onChange={(e) => setProfileName(e.target.value)} className="w-full px-4 py-3 rounded-xl bg-fintrix-surface-2/70 border border-fintrix-border-subtle text-fintrix-text text-sm focus:outline-none focus:border-fintrix-primary/50" />
              </div>

              <div>
                <label className="block text-xs font-medium text-fintrix-text-muted mb-1.5 uppercase tracking-wider">New Password</label>
                <input type="password" value={profilePassword} onChange={(e) => setProfilePassword(e.target.value)} placeholder="Leave blank to keep current" className="w-full px-4 py-3 rounded-xl bg-fintrix-surface-2/70 border border-fintrix-border-subtle text-fintrix-text placeholder-fintrix-text-dimmed text-sm focus:outline-none focus:border-fintrix-primary/50" />
              </div>

              {profileMessage && (
                <div className={`p-3 rounded-lg text-sm ${profileMessage.startsWith("Error") ? "bg-red-500/10 text-red-400" : "bg-emerald-500/10 text-emerald-400"}`}>
                  {profileMessage}
                </div>
              )}

              <button onClick={updateProfile} className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-fintrix-primary to-fintrix-accent text-white text-sm font-medium cursor-pointer hover:shadow-lg hover:shadow-fintrix-primary/25 transition-all">
                Save Changes
              </button>
            </div>
          )}

          {/* Scheduler */}
          {activeSection === "scheduler" && (
            <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle space-y-5">
              <div>
                <h3 className="text-lg font-semibold text-fintrix-text mb-1">Scheduler</h3>
                <p className="text-sm text-fintrix-text-muted">Automated reconciliation and sync jobs.</p>
              </div>

              {scheduler ? (
                <>
                  <div className="flex items-center gap-2 mb-4">
                    <span className={`status-dot ${scheduler.status === "running" ? "status-dot-active" : "status-dot-danger"}`} />
                    <span className="text-sm text-fintrix-text">{scheduler.status === "running" ? "Scheduler Running" : "Scheduler Stopped"}</span>
                  </div>

                  <div className="space-y-2">
                    {scheduler.jobs.map((job) => (
                      <div key={job.id} className="p-4 rounded-xl bg-fintrix-surface-2/30 border border-fintrix-border-subtle">
                        <div className="flex justify-between items-start">
                          <div>
                            <p className="text-sm text-fintrix-text font-medium">{job.name}</p>
                            <p className="text-xs text-fintrix-text-dimmed font-mono mt-1">{job.trigger}</p>
                          </div>
                          <div className="text-right">
                            <p className="text-xs text-fintrix-text-muted">Next Run</p>
                            <p className="text-xs text-fintrix-text-dimmed font-mono">
                              {job.next_run ? new Date(job.next_run).toLocaleString() : "—"}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                    {scheduler.jobs.length === 0 && (
                      <p className="text-sm text-fintrix-text-dimmed text-center py-4">No scheduled jobs.</p>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-sm text-fintrix-text-dimmed">Unable to fetch scheduler status.</p>
              )}
            </div>
          )}

          {/* Razorpay */}
          {activeSection === "razorpay" && (
            <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle space-y-5">
              <div>
                <h3 className="text-lg font-semibold text-fintrix-text mb-1">Razorpay Integration</h3>
                <p className="text-sm text-fintrix-text-muted">Configure your Razorpay connection.</p>
              </div>

              <div className="p-4 rounded-xl bg-blue-500/10 border border-blue-500/20">
                <p className="text-sm text-blue-400 font-medium mb-2 flex items-center gap-1.5"><span className="material-symbols-outlined icon-sm">credit_card</span> Integration Setup</p>
                <p className="text-xs text-fintrix-text-dimmed">
                  Configure your Razorpay credentials in the <code className="text-blue-400">.env</code> file:
                </p>
                <pre className="mt-2 p-3 rounded-lg bg-fintrix-surface-2/80 text-xs font-mono text-fintrix-text-dimmed overflow-x-auto">
{`RAZORPAY_KEY_ID=rzp_test_xxxxx
RAZORPAY_KEY_SECRET=xxxxx
RAZORPAY_WEBHOOK_SECRET=xxxxx`}
                </pre>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 rounded-xl bg-fintrix-surface-2/30 border border-fintrix-border-subtle">
                  <span className="text-sm text-fintrix-text">Webhook Endpoint</span>
                  <code className="text-xs text-fintrix-text-dimmed font-mono">/api/webhooks/razorpay</code>
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl bg-fintrix-surface-2/30 border border-fintrix-border-subtle">
                  <span className="text-sm text-fintrix-text">Signature Verification</span>
                  <span className="text-xs text-emerald-400">HMAC-SHA256</span>
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl bg-fintrix-surface-2/30 border border-fintrix-border-subtle">
                  <span className="text-sm text-fintrix-text">Auto-sync</span>
                  <span className="text-xs text-fintrix-text-muted">Every 15 minutes</span>
                </div>
              </div>
            </div>
          )}

          {/* Export */}
          {activeSection === "export" && (
            <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle space-y-5">
              <div>
                <h3 className="text-lg font-semibold text-fintrix-text mb-1">Export Data</h3>
                <p className="text-sm text-fintrix-text-muted">Download data as CSV files.</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                {[
                  { label: "Transactions", icon: "receipt_long", desc: "All payment/refund records", action: () => alert("Exporting Transactions is disabled in the hackathon demo.") },
                  { label: "Exceptions", icon: "warning", desc: "All detected exceptions", action: () => alert("Exporting Exceptions is disabled in the hackathon demo.") },
                  { label: "Audit Trail", icon: "history", desc: "Complete audit log", action: () => alert("Exporting Audit Trail is disabled in the hackathon demo.") },
                ].map((item) => (
                  <button
                    key={item.label}
                    onClick={item.action}
                    className="p-4 rounded-xl bg-fintrix-surface-2/30 border border-fintrix-border-subtle hover:border-fintrix-primary/30 transition-all text-left cursor-pointer group"
                  >
                    <span className="material-symbols-outlined text-fintrix-text-muted group-hover:text-fintrix-primary transition-colors" style={{ fontSize: "28px" }}>{item.icon}</span>
                    <p className="text-sm text-fintrix-text font-medium mt-2 group-hover:text-fintrix-primary transition-colors">{item.label}</p>
                    <p className="text-xs text-fintrix-text-dimmed mt-0.5">{item.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Diagnostics */}
          {activeSection === "diagnostics" && (
            <div className="glass-card rounded-xl p-6 border border-fintrix-border-subtle space-y-5 animate-fadeIn">
              <div>
                <h3 className="text-lg font-semibold text-fintrix-text mb-1">System Diagnostics</h3>
                <p className="text-sm text-fintrix-text-muted">Run self-checks and system validation tests.</p>
              </div>

              <div className="p-4 rounded-xl bg-fintrix-surface-2/30 border border-fintrix-border-subtle">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h4 className="text-sm font-medium text-fintrix-text">Pipeline Determinism Test</h4>
                    <p className="text-xs text-fintrix-text-dimmed mt-1">
                      Verifies that running the pipeline multiple times produces identical results. 
                      Ensures reliability of the AI and rules engines.
                    </p>
                  </div>
                  <button
                    onClick={async () => {
                      setRunningDeterminism(true);
                      setDeterminismResult(null);
                      try {
                        const result = await api.runDeterminismTest();
                        setDeterminismResult(result);
                      } catch (err: any) {
                        setDeterminismResult({ error: err.message });
                      } finally {
                        setRunningDeterminism(false);
                      }
                    }}
                    disabled={runningDeterminism}
                    className="px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 border border-blue-500/30 text-sm font-medium transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
                  >
                    {runningDeterminism ? (
                      <><div className="w-4 h-4 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" /> Running...</>
                    ) : "Run Test"}
                  </button>
                </div>

                {determinismResult && (
                  <div className={`mt-4 p-4 rounded-lg border ${
                    determinismResult.error ? 'bg-red-500/10 border-red-500/20' :
                    determinismResult.passed ? 'bg-emerald-500/10 border-emerald-500/20' : 
                    'bg-amber-500/10 border-amber-500/20'
                  }`}>
                    {determinismResult.error ? (
                      <p className="text-sm text-red-400">{determinismResult.error}</p>
                    ) : (
                      <div className="space-y-3">
                        <div className="flex items-center gap-2">
                          <span className={determinismResult.passed ? 'text-emerald-400' : 'text-amber-400'}>
                            {determinismResult.passed ? '✓ Test Passed' : '⚠ Test Failed'}
                          </span>
                        </div>
                        
                        <div className="grid grid-cols-2 gap-4 text-sm">
                          <div>
                            <p className="text-xs text-fintrix-text-muted mb-1">Run 1 Output</p>
                            <div className="bg-black/30 p-2 rounded text-fintrix-text-dimmed font-mono text-[10px]">
                              {JSON.stringify(determinismResult.results.run_1, null, 2)}
                            </div>
                          </div>
                          <div>
                            <p className="text-xs text-fintrix-text-muted mb-1">Run 2 Output</p>
                            <div className="bg-black/30 p-2 rounded text-fintrix-text-dimmed font-mono text-[10px]">
                              {JSON.stringify(determinismResult.results.run_2, null, 2)}
                            </div>
                          </div>
                        </div>
                        
                        {!determinismResult.passed && determinismResult.diffs && (
                          <div>
                            <p className="text-xs text-amber-400/80 uppercase tracking-wider mb-1">Detected Differences</p>
                            <ul className="list-disc list-inside text-xs text-amber-400">
                              {determinismResult.diffs.map((diff: string, i: number) => (
                                <li key={i}>{diff}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
