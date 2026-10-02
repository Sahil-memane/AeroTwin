import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { authApi } from "@/services/resources";
import { ApiError } from "@/services/apiClient";
import type { Role } from "@/types";

// ── Validation helpers ─────────────────────────────────────────────────────
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validate(fields: {
  fullName: string;
  email: string;
  password: string;
  confirmPassword: string;
  role: string;
}) {
  const errors: Partial<Record<keyof typeof fields, string>> = {};
  if (!fields.fullName.trim() || fields.fullName.trim().length < 2)
    errors.fullName = "Full name must be at least 2 characters.";
  if (!EMAIL_RE.test(fields.email)) errors.email = "Enter a valid email address.";
  if (fields.password.length < 12)
    errors.password = "Password must be at least 12 characters.";
  if (!/[A-Z]/.test(fields.password))
    errors.password = "Password must contain at least one uppercase letter.";
  if (!/[0-9]/.test(fields.password))
    errors.password = "Password must contain at least one number.";
  if (fields.password !== fields.confirmPassword)
    errors.confirmPassword = "Passwords do not match.";
  if (!fields.role) errors.role = "Select a role.";
  return errors;
}

const ROLES: { value: Role; label: string; desc: string }[] = [
  { value: "operator", label: "Operator", desc: "View telemetry, alerts and engine status" },
  { value: "maintenance_engineer", label: "Maintenance Engineer", desc: "Log maintenance actions and view diagnostics" },
  { value: "program_manager", label: "Program Manager", desc: "Fleet-level reporting and mission oversight" },
];

// ── Password strength indicator ────────────────────────────────────────────
function PasswordStrength({ password }: { password: string }) {
  const checks = [
    { label: "12+ chars", ok: password.length >= 12 },
    { label: "Uppercase", ok: /[A-Z]/.test(password) },
    { label: "Number", ok: /[0-9]/.test(password) },
    { label: "Symbol", ok: /[^A-Za-z0-9]/.test(password) },
  ];
  const score = checks.filter((c) => c.ok).length;
  const barColor =
    score <= 1 ? "bg-critical" : score === 2 ? "bg-yellow-500" : score === 3 ? "bg-orange-400" : "bg-emerald-500";
  const label = ["Weak", "Fair", "Good", "Strong"][score - 1] ?? "";

  if (!password) return null;

  return (
    <div className="flex flex-col gap-1.5 mt-1">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1 rounded-full bg-surface2 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${barColor}`}
            style={{ width: `${(score / 4) * 100}%` }}
          />
        </div>
        <span className="text-[10px] font-mono tracking-wider text-textMuted">{label}</span>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {checks.map((c) => (
          <span
            key={c.label}
            className={`text-[10px] font-mono ${c.ok ? "text-emerald-400" : "text-textFaint"}`}
          >
            {c.ok ? "✓" : "○"} {c.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Main Register component ────────────────────────────────────────────────
export function Register() {
  const navigate = useNavigate();
  const storeLogin = useAuthStore((s) => s.login);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState<string>("operator");
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState<Partial<Record<string, boolean>>>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const errors = validate({ fullName, email, password, confirmPassword, role });
  const isValid = Object.keys(errors).length === 0;

  function touch(field: string) {
    setTouched((prev) => ({ ...prev, [field]: true }));
  }

  function fieldError(field: string) {
    return touched[field] ? (errors as Record<string, string>)[field] : undefined;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Mark all touched so every error shows
    setTouched({ fullName: true, email: true, password: true, confirmPassword: true, role: true });
    if (!isValid) return;

    setApiError(null);
    setLoading(true);
    try {
      const tokens = await authApi.register({ email, password, full_name: fullName, role });
      storeLogin({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        role: tokens.role as Role,
        email,
      });
      navigate("/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) setApiError("An account with this email already exists.");
        else if (err.status === 422) setApiError("Invalid input — check your details and try again.");
        else if (err.status === 429) setApiError("Too many attempts — please wait a moment.");
        else setApiError("Registration failed. Please try again.");
      } else {
        setApiError("Could not reach the AeroTwin backend.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-bg font-sans text-text py-10">
      <form
        onSubmit={handleSubmit}
        noValidate
        className="flex w-[440px] flex-col gap-5 rounded-sm border border-border bg-surface p-9"
      >
        {/* Header */}
        <div>
          <div className="text-xl font-bold tracking-wide">
            AERO<span className="text-accent">TWIN</span>
          </div>
          <div className="mt-1 text-[11px] tracking-wider text-textFaint">CREATE OPERATOR ACCOUNT</div>
        </div>

        <div className="h-px bg-border" />

        {/* Full Name */}
        <Field label="Full Name" error={fieldError("fullName")}>
          <input
            id="reg-fullname"
            type="text"
            autoComplete="name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            onBlur={() => touch("fullName")}
            placeholder="e.g. Arjun Verma"
            className={inputCls(!!fieldError("fullName"))}
          />
        </Field>

        {/* Email */}
        <Field label="Email Address" error={fieldError("email")}>
          <input
            id="reg-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => touch("email")}
            placeholder="you@organisation.in"
            className={inputCls(!!fieldError("email"))}
          />
        </Field>

        {/* Password */}
        <Field label="Password" error={fieldError("password")}>
          <div className="relative">
            <input
              id="reg-password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onBlur={() => touch("password")}
              placeholder="Min. 12 characters"
              className={inputCls(!!fieldError("password")) + " pr-10"}
            />
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] text-textFaint hover:text-textMuted transition-colors"
            >
              {showPassword ? "HIDE" : "SHOW"}
            </button>
          </div>
          <PasswordStrength password={password} />
        </Field>

        {/* Confirm Password */}
        <Field label="Confirm Password" error={fieldError("confirmPassword")}>
          <input
            id="reg-confirm"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            onBlur={() => touch("confirmPassword")}
            placeholder="Re-enter your password"
            className={inputCls(!!fieldError("confirmPassword"))}
          />
        </Field>

        {/* Role */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] font-semibold uppercase tracking-wide text-textMuted">Role</label>
          <div className="flex flex-col gap-2">
            {ROLES.map((r) => (
              <label
                key={r.value}
                className={`flex items-start gap-3 rounded-sm border px-3 py-2.5 cursor-pointer transition-colors ${
                  role === r.value
                    ? "border-accent bg-accent/5"
                    : "border-border bg-surface2 hover:border-borderStrong"
                }`}
              >
                <input
                  type="radio"
                  name="role"
                  value={r.value}
                  checked={role === r.value}
                  onChange={() => { setRole(r.value); touch("role"); }}
                  className="mt-0.5 accent-accent"
                />
                <div>
                  <div className={`text-xs font-semibold tracking-wide ${role === r.value ? "text-accent" : "text-text"}`}>
                    {r.label}
                  </div>
                  <div className="text-[10px] text-textFaint mt-0.5">{r.desc}</div>
                </div>
              </label>
            ))}
          </div>
          {fieldError("role") && <p className="text-[10px] text-critical">{fieldError("role")}</p>}
        </div>

        {/* API Error */}
        {apiError && (
          <div className="rounded-sm border border-critical/40 bg-critical/10 px-3 py-2 text-xs text-critical">
            {apiError}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="rounded-sm bg-accent py-2.5 text-sm font-semibold text-bg hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Creating account…" : "Create Account"}
        </button>

        {/* Link back */}
        <div className="text-center text-[11px] text-textFaint">
          Already have an account?{" "}
          <Link to="/login" className="text-accent hover:underline">
            Sign In
          </Link>
        </div>

        <div className="text-center text-[10px] text-textFaint leading-relaxed">
          Admin accounts can only be created by an existing administrator.
        </div>
      </form>
    </div>
  );
}

// ── Shared sub-components ──────────────────────────────────────────────────
function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[11px] font-semibold uppercase tracking-wide text-textMuted">{label}</label>
      {children}
      {error && <p className="text-[10px] text-critical">{error}</p>}
    </div>
  );
}

function inputCls(hasError: boolean) {
  return `rounded-sm border ${
    hasError ? "border-critical" : "border-borderStrong"
  } bg-surface2 px-2.5 py-2 font-mono text-sm outline-none focus:border-accent w-full transition-colors`;
}
