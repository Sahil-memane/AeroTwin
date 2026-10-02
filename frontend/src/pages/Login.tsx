import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

// ── Guest account (intentionally visible — read-only operator demo) ──────────
const GUEST_EMAIL = "guest@aerotwin.demo";
const GUEST_PASSWORD = "guest-aerotwin-2026";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState(import.meta.env.DEV ? "admin@aerotwin-dev.com" : "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [guestLoading, setGuestLoading] = useState(false);
  const [guestError, setGuestError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const result = await login(email, password);
    setLoading(false);
    if (result.ok) {
      navigate("/dashboard", { replace: true });
    } else {
      setError(result.error);
    }
  }

  async function handleGuestLogin() {
    setGuestError(null);
    setGuestLoading(true);
    const result = await login(GUEST_EMAIL, GUEST_PASSWORD);
    setGuestLoading(false);
    if (result.ok) {
      navigate("/dashboard", { replace: true });
    } else {
      setGuestError(result.error ?? "Guest login unavailable.");
    }
  }

  return (
    <div className="flex h-screen w-full items-center justify-center bg-bg font-sans text-text">
      <form
        onSubmit={handleSubmit}
        className="flex w-[400px] flex-col gap-5 rounded-sm border border-border bg-surface p-9"
      >
        <div>
          <div className="text-xl font-bold tracking-wide">
            AERO<span className="text-accent">TWIN</span>
          </div>
          <div className="mt-1 text-[11px] tracking-wider text-textFaint">DIGITAL TWIN OPERATOR CONSOLE</div>
        </div>

        <div className="h-px bg-border" />

        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] font-semibold uppercase tracking-wide text-textMuted">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="rounded-sm border border-borderStrong bg-surface2 px-2.5 py-2 font-mono text-sm outline-none focus:border-accent"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] font-semibold uppercase tracking-wide text-textMuted">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="rounded-sm border border-borderStrong bg-surface2 px-2.5 py-2 font-mono text-sm outline-none focus:border-accent"
          />
        </div>

        {error && <div className="text-xs text-critical">{error}</div>}

        <button
          type="submit"
          disabled={loading}
          className="rounded-sm bg-accent py-2.5 text-sm font-semibold text-bg disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign In"}
        </button>

        {/* OR divider */}
        <div className="relative flex items-center gap-3">
          <div className="h-px flex-1 bg-border" />
          <span className="text-[10px] uppercase tracking-widest text-textFaint">or</span>
          <div className="h-px flex-1 bg-border" />
        </div>

        {/* Guest / bypass button */}
        <div className="flex flex-col gap-1.5">
          <button
            type="button"
            onClick={handleGuestLogin}
            disabled={guestLoading}
            className="flex items-center justify-center gap-2 rounded-sm border border-border bg-surface2 py-2.5 text-sm font-semibold text-textMuted hover:border-accent hover:text-accent transition-colors disabled:opacity-50"
          >
            {guestLoading ? (
              "Signing in as guest…"
            ) : (
              <>
                <span className="font-mono text-[10px]">⬡</span>
                Continue as Guest &nbsp;<span className="text-[10px] opacity-60">(Read-Only Demo)</span>
              </>
            )}
          </button>
          {guestError && <div className="text-xs text-critical text-center">{guestError}</div>}
        </div>

        <div className="text-center text-[11px] text-textFaint">
          Access requires an operator, maintenance engineer, program manager, or admin role.
        </div>

        <div className="text-center text-[11px] text-textFaint">
          Don&apos;t have an account?{" "}
          <Link to="/register" className="text-accent hover:underline">
            Create one
          </Link>
        </div>
      </form>
    </div>
  );
}
