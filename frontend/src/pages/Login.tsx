import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState(import.meta.env.DEV ? "admin@aerotwin-dev.com" : "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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

        <div className="text-center text-[11px] text-textFaint">
          Access requires an operator, maintenance engineer, program manager, or admin role.
        </div>
      </form>
    </div>
  );
}
