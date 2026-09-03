import { useState } from "react";
import { api } from "../api";

interface LoginProps {
  onLogin: () => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("admin@fintrix.io");
  const [password, setPassword] = useState("admin123");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      if (mode === "login") {
        await api.login(email, password);
      } else {
        if (!name.trim()) {
          setError("Name is required");
          setLoading(false);
          return;
        }
        await api.register(email, password, name);
      }
      onLogin();
    } catch (err: any) {
      setError(err.message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-fintrix-bg flex items-center justify-center bg-grid-pattern p-4">
      {/* Ambient glow */}
      <div className="fixed top-1/4 left-1/3 w-[500px] h-[500px] bg-fintrix-primary/4 rounded-full blur-[140px] pointer-events-none" />
      <div className="fixed bottom-1/4 right-1/3 w-[400px] h-[400px] bg-fintrix-accent/3 rounded-full blur-[140px] pointer-events-none" />

      <div className="relative w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-fintrix-primary to-fintrix-accent text-white text-2xl font-black shadow-2xl shadow-fintrix-primary/30 mb-5 animate-logo-glow">
            F
          </div>
          <h1 className="text-3xl font-bold gradient-text tracking-tight">Fintrix</h1>
          <p className="text-fintrix-text-muted text-sm mt-1.5 tracking-widest uppercase font-medium">
            AI Finance Controller
          </p>
        </div>

        {/* Card */}
        <div className="glass-card rounded-2xl p-8 border border-fintrix-border-subtle shadow-2xl">
          {/* Tab toggle */}
          <div className="flex rounded-xl bg-fintrix-surface-2/50 p-1 mb-6">
            <button
              onClick={() => { setMode("login"); setError(""); }}
              className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${
                mode === "login"
                  ? "bg-fintrix-primary/15 text-fintrix-primary shadow-sm"
                  : "text-fintrix-text-muted hover:text-fintrix-text"
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setMode("register"); setError(""); }}
              className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${
                mode === "register"
                  ? "bg-fintrix-primary/15 text-fintrix-primary shadow-sm"
                  : "text-fintrix-text-muted hover:text-fintrix-text"
              }`}
            >
              Register
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "register" && (
              <div>
                <label className="block text-xs font-medium text-fintrix-text-muted mb-1.5 uppercase tracking-wider">
                  Full Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  className="w-full px-4 py-3 rounded-xl bg-fintrix-surface-2/70 border border-fintrix-border-subtle text-fintrix-text placeholder-fintrix-text-dimmed text-sm input-glow"
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-fintrix-text-muted mb-1.5 uppercase tracking-wider">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="w-full px-4 py-3 rounded-xl bg-fintrix-surface-2/70 border border-fintrix-border-subtle text-fintrix-text placeholder-fintrix-text-dimmed text-sm input-glow"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-fintrix-text-muted mb-1.5 uppercase tracking-wider">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                minLength={6}
                className="w-full px-4 py-3 rounded-xl bg-fintrix-surface-2/70 border border-fintrix-border-subtle text-fintrix-text placeholder-fintrix-text-dimmed text-sm input-glow"
              />
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-fintrix-primary to-fintrix-accent text-white font-medium text-sm transition-all hover:shadow-lg hover:shadow-fintrix-primary/25 active:shadow-md disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                  {mode === "login" ? "Signing in..." : "Creating account..."}
                </span>
              ) : (
                mode === "login" ? "Sign In" : "Create Account"
              )}
            </button>
          </form>

          {mode === "login" && (
            <div className="mt-4 p-3 rounded-lg bg-fintrix-surface-2/50 border border-fintrix-border-subtle">
              <p className="text-[11px] text-fintrix-text-dimmed">
                <span className="text-fintrix-text-muted font-medium">Demo credentials: </span>
                admin@fintrix.io / admin123
              </p>
            </div>
          )}
        </div>

        <p className="text-center text-[11px] text-fintrix-text-dimmed mt-6">
          Razorpay AI Buildathon · Track 4 · Finance Controller
        </p>
      </div>
    </div>
  );
}
