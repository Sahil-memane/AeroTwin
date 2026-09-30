import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { enginesApi, simulationApi } from "@/services/resources";
import { fmtDateTime, parseBackendTs } from "@/lib/utils";
import type { TelemetryReading, WhatIfConfig, WhatIfParam, WhatIfResponse, WhatIfValues } from "@/types";
import { WHAT_IF_PARAMS } from "@/types";
import { WhatIfResults } from "./WhatIfResults";
import { PARAM_LABELS, STALE_AFTER_MS, changedParameters, describeWhatIfError, differs, fmtAge, fmtNum, fmtSigned } from "./whatIfFormat";

// The backend's first call in a fresh process lazy-loads four ML models
// (~2-4 s cold); 60 s is a generous ceiling before we call it a timeout.
const REQUEST_TIMEOUT_MS = 60_000;
const SIM = "#C9962F";
const LATEST = "latest";

const MODEL_LABEL: Record<string, string> = { rul: "RUL", fault: "Fault", bearing: "Bearing", auxiliary: "Aux" };

function toValues(t: TelemetryReading): WhatIfValues {
  return {
    rpm: t.rpm,
    cht: t.cht,
    egt: t.egt,
    oil_pressure: t.oil_pressure,
    oil_temperature: t.oil_temp,
    fuel_flow: t.fuel_flow,
  };
}

export interface BaselineOption {
  value: string;
  label: string;
}

/** Up to ~12 evenly spaced past moments from the health history, plus the best-scoring one. */
export function buildBaselineOptions(history: { ts: string; combined_score: number }[]): BaselineOption[] {
  if (history.length === 0) return [];
  const best = history.reduce((a, b) => (b.combined_score > a.combined_score ? b : a));
  const step = Math.max(1, Math.floor(history.length / 12));
  const picked = new Map<string, { ts: string; combined_score: number; tag?: string }>();
  for (let i = history.length - 1; i >= 0; i -= step) picked.set(history[i].ts, history[i]);
  picked.set(best.ts, { ...best, tag: "best recent" });
  return [...picked.values()]
    .sort((a, b) => (a.ts < b.ts ? 1 : -1))
    .map((h) => ({ value: h.ts, label: `${fmtDateTime(h.ts)} · health ${fmtNum(h.combined_score)}${h.tag ? ` (${h.tag})` : ""}` }));
}

function ParamCard({
  param,
  config,
  current,
  value,
  disabled,
  onChange,
}: {
  param: WhatIfParam;
  config: WhatIfConfig;
  current: number;
  value: number;
  disabled: boolean;
  onChange: (v: number) => void;
}) {
  const cfg = config.parameters[param];
  const delta = value - current;
  const changed = differs(value, current);
  const span = cfg.max - cfg.min;
  const currentPct = Math.max(0, Math.min(100, ((current - cfg.min) / span) * 100));
  const feeds = Object.entries(config.feature_mapping ?? {})
    .filter(([, m]) => m.direct.includes(param))
    .map(([k]) => MODEL_LABEL[k] ?? k);

  return (
    <div
      className={`min-w-0 rounded-sm border bg-surface p-4 transition-colors ${changed ? "border-accent" : "border-border"}`}
      data-testid={`whatif-row-${param}`}
    >
      <div className="mb-2 flex min-h-[26px] items-center gap-2">
        <div className="text-xs font-semibold">{PARAM_LABELS[param]}</div>
        <span className="text-[10px] text-textFaint">{cfg.unit}</span>
        <span className="flex-grow" />
        {changed && (
          <button
            type="button"
            onClick={() => onChange(current)}
            disabled={disabled}
            aria-label={`Reset ${PARAM_LABELS[param]}`}
            className="rounded-sm border border-borderStrong px-1.5 py-0.5 text-[10px] text-textMuted hover:border-accent hover:text-accent"
          >
            ↺ reset
          </button>
        )}
      </div>

      <div className="mb-3 flex items-end gap-3">
        <div>
          <div className="text-[10px] uppercase text-textFaint">Scenario</div>
          <div className="flex items-center gap-1.5">
            <input
              type="number"
              aria-label={`${PARAM_LABELS[param]} scenario value`}
              min={cfg.min}
              max={cfg.max}
              step={cfg.step}
              value={Number(value.toFixed(2))}
              disabled={disabled}
              onChange={(e) => e.target.value !== "" && onChange(Number(e.target.value))}
              className="w-[104px] rounded-sm border border-borderStrong bg-surface2 px-2 py-1 font-mono text-lg font-semibold outline-none focus:border-accent"
              data-testid={`whatif-scenario-${param}`}
            />
            <span className="font-mono text-xs text-textFaint">{cfg.unit}</span>
          </div>
        </div>
        <div className="pb-1.5">
          <div className="text-[10px] uppercase text-textFaint">Current</div>
          <div className="font-mono text-xs text-textMuted" data-testid={`whatif-current-${param}`}>
            {fmtNum(current)} {cfg.unit}
          </div>
        </div>
        <span className="flex-grow" />
        <span
          className={`mb-1.5 flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[11px] ${
            changed ? "border-accent font-semibold text-accent" : "border-borderStrong text-textFaint"
          }`}
        >
          {changed && <span aria-hidden>{delta > 0 ? "▲" : "▼"}</span>}
          <span data-testid={`whatif-delta-${param}`}>
            {fmtSigned(delta)} {cfg.unit}
          </span>
        </span>
      </div>

      <div className="relative">
        <input
          type="range"
          aria-label={`${PARAM_LABELS[param]} scenario`}
          min={cfg.min}
          max={cfg.max}
          step={cfg.step}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))}
          className="relative z-10 w-full accent-accent"
        />
        {/* marker for where the engine actually is right now */}
        <span
          aria-hidden
          title={`current ${fmtNum(current)} ${cfg.unit}`}
          className="pointer-events-none absolute top-1/2 z-0 h-4 w-0.5 -translate-y-1/2 bg-textMuted"
          style={{ left: `calc(${currentPct}% + ${(0.5 - currentPct / 100) * 16}px)` }}
        />
      </div>
      <div className="mt-0.5 flex justify-between font-mono text-[10px] text-textFaint">
        <span>{cfg.min}</span>
        <span>{cfg.max}</span>
      </div>

      {feeds.length > 0 && (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-border pt-2">
          <span className="text-[10px] uppercase text-textFaint">Feeds</span>
          {feeds.map((f) => (
            <span key={f} className="rounded-sm border border-borderStrong px-1.5 py-0.5 text-[10px] text-textMuted">
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

interface WhatIfPanelProps {
  engineId: string;
}

export function WhatIfPanel({ engineId }: WhatIfPanelProps) {
  const [config, setConfig] = useState<WhatIfConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryReading | null>(null);
  const [telemetryState, setTelemetryState] = useState<"loading" | "ready" | "unavailable">("loading");
  const [baselineChoice, setBaselineChoice] = useState<string>(LATEST);
  const [baselineOptions, setBaselineOptions] = useState<BaselineOption[]>([]);

  // Scenario state is purely local: sliders never touch live telemetry,
  // engine state, alerts, the DB, or Replay state.
  const [scenario, setScenario] = useState<WhatIfValues | null>(null);

  const [calculating, setCalculating] = useState(false);
  const [result, setResult] = useState<WhatIfResponse | null>(null);
  const [ranKey, setRanKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0); // invalidates in-flight responses on Reset / baseline change / engine change

  const clearOutcome = useCallback(() => {
    requestId.current += 1;
    setResult(null);
    setRanKey(null);
    setError(null);
    setCalculating(false);
  }, []);

  const loadBaseline = useCallback(
    async (choice: string) => {
      setTelemetryState("loading");
      try {
        const reading = choice === LATEST ? await enginesApi.telemetryLatest(engineId) : await enginesApi.telemetryAt(engineId, choice);
        if (!reading) throw new Error("no reading");
        setTelemetry(reading);
        setScenario(toValues(reading));
        setTelemetryState("ready");
      } catch {
        setTelemetry(null);
        setScenario(null);
        setTelemetryState("unavailable");
      }
    },
    [engineId],
  );

  useEffect(() => {
    clearOutcome();
    setBaselineChoice(LATEST);
    setBaselineOptions([]);
    simulationApi
      .whatIfConfig()
      .then((c) => {
        setConfig(c);
        setConfigError(null);
      })
      .catch(() => setConfigError("Couldn't load What-If parameter ranges from the server."));
    void loadBaseline(LATEST);
    // Health history powers the optional "baseline at an earlier moment" picker; best-effort.
    Promise.resolve(enginesApi.healthScore(engineId, 1500))
      .then((res) => setBaselineOptions(buildBaselineOptions(res?.history ?? [])))
      .catch(() => setBaselineOptions([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engineId]);

  const current = useMemo(() => (telemetry ? toValues(telemetry) : null), [telemetry]);
  const changed = current && scenario ? changedParameters(current, scenario, WHAT_IF_PARAMS) : {};
  const changedCount = Object.keys(changed).length;
  const stale = result !== null && ranKey !== JSON.stringify(changed);
  const canRun = !!current && !!config && changedCount > 0 && !calculating;
  const isLatest = baselineChoice === LATEST;
  const ageMs = telemetry ? Date.now() - parseBackendTs(telemetry.ts).getTime() : 0;

  function setValue(param: WhatIfParam, raw: number) {
    if (!config || !Number.isFinite(raw)) return;
    const { min, max } = config.parameters[param];
    setScenario((prev) => (prev ? { ...prev, [param]: Math.min(max, Math.max(min, raw)) } : prev));
  }

  function reset() {
    clearOutcome();
    if (current) setScenario(current);
  }

  // A new baseline invalidates any previous result (it was computed against the old one).
  function refreshCurrent() {
    clearOutcome();
    setBaselineChoice(LATEST);
    void loadBaseline(LATEST);
  }

  function chooseBaseline(choice: string) {
    clearOutcome();
    setBaselineChoice(choice);
    void loadBaseline(choice);
  }

  async function run() {
    if (!canRun || !current) return;
    const id = ++requestId.current;
    setCalculating(true);
    setError(null);
    const sent = { ...changed };
    try {
      const res = await simulationApi.runParameterWhatIf(engineId, sent, telemetry?.ts, REQUEST_TIMEOUT_MS);
      if (id !== requestId.current) return;
      setResult(res);
      setRanKey(JSON.stringify(sent));
    } catch (e) {
      if (id !== requestId.current) return;
      setError(describeWhatIfError(e));
    } finally {
      if (id === requestId.current) setCalculating(false);
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-3.5" data-testid="whatif-panel">
      {/* Intro + baseline */}
      <div className="rounded-sm border border-border bg-surface p-4">
        <div className="mb-1 text-[15px] font-semibold">Engine parameter What-If</div>
        <div className="text-xs text-textMuted">
          Change engine operating parameters → RUN WHAT-IF → see how AeroTwin&apos;s actual RUL, fault, bearing and auxiliary models and Health
          Fusion respond. Nothing here changes the live engine.
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-sm border border-border bg-surface2 px-3 py-2" data-testid="whatif-live">
          <span
            className={`rounded-sm border px-2 py-0.5 text-[10px] font-bold tracking-wider ${isLatest ? "border-healthy text-healthy" : "border-borderStrong text-textMuted"}`}
            data-testid="whatif-live-badge"
          >
            {isLatest ? "LIVE ENGINE" : "HISTORICAL BASELINE"}
          </span>
          {telemetryState === "loading" && <span className="text-xs text-textMuted">Loading baseline telemetry…</span>}
          {telemetryState === "unavailable" && (
            <span className="text-xs text-textMuted" data-testid="whatif-unavailable">
              Current engine data unavailable — What-If needs a real baseline, so no values are shown or substituted.
            </span>
          )}
          {telemetry && (
            <>
              <span className="font-mono text-[11px] text-textMuted">
                as of {fmtDateTime(telemetry.ts)} · {fmtAge(ageMs)} ago
              </span>
              <span className="flex-grow" />
              <label className="flex items-center gap-1.5 text-[11px] text-textMuted">
                Baseline
                <select
                  value={baselineChoice}
                  onChange={(e) => chooseBaseline(e.target.value)}
                  disabled={calculating}
                  aria-label="Baseline moment"
                  data-testid="whatif-baseline-select"
                  className="max-w-[300px] rounded-sm border border-borderStrong bg-surface px-1.5 py-1 text-[11px] text-text"
                >
                  <option value={LATEST}>Latest stored reading</option>
                  {baselineOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <button onClick={refreshCurrent} className="text-[11px] text-accent hover:underline" data-testid="whatif-refresh">
                Refresh current
              </button>
            </>
          )}
        </div>
      </div>

      {telemetry && isLatest && ageMs > STALE_AFTER_MS && (
        <div className="rounded-sm border border-warning bg-warningBg px-3 py-2 text-xs text-warning" data-testid="whatif-old-telemetry">
          The latest stored reading is {fmtAge(ageMs)} old — the engine doesn&apos;t appear to be streaming. What-If uses the most recent stored
          telemetry window, not a live one.
        </div>
      )}

      {configError && (
        <div role="alert" className="rounded-sm border border-critical bg-criticalBg px-3 py-2 text-xs text-critical" data-testid="whatif-config-error">
          {configError}
        </div>
      )}

      {/* Scenario controls */}
      {current && scenario && config && (
        <div className="flex min-w-0 flex-col gap-3" data-testid="whatif-controls">
          <div
            className="sticky top-0 z-20 flex flex-wrap items-center gap-2.5 rounded-sm border border-dashed bg-surface px-4 py-2.5 shadow-[0_6px_12px_-8px_rgba(0,0,0,0.6)]"
            style={{ borderColor: SIM }}
          >
            <span className="rounded-sm border px-2 py-0.5 text-[10px] font-bold tracking-wider" style={{ borderColor: SIM, color: SIM }}>
              WHAT-IF SIMULATION
            </span>
            <span className="text-[11px] text-textMuted">
              Scenario: {changedCount === 0 ? "matches baseline" : `Custom (${changedCount} parameter${changedCount > 1 ? "s" : ""} changed)`}
            </span>
            <span className="flex-grow" />
            <button
              onClick={reset}
              className="rounded-sm border border-borderStrong bg-surface2 px-3 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent"
              data-testid="whatif-reset"
            >
              RESET TO CURRENT
            </button>
            <button
              onClick={() => void run()}
              disabled={!canRun}
              className="rounded-sm bg-accent px-4 py-1.5 text-xs font-semibold text-bg disabled:opacity-50"
              data-testid="whatif-run"
            >
              {calculating ? "CALCULATING…" : "RUN WHAT-IF"}
            </button>
          </div>

          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            {WHAT_IF_PARAMS.map((p) => (
              <ParamCard
                key={p}
                param={p}
                config={config}
                current={current[p]}
                value={scenario[p]}
                disabled={calculating}
                onChange={(v) => setValue(p, v)}
              />
            ))}
          </div>
          {changedCount === 0 && (
            <div className="text-[11px] text-textFaint" data-testid="whatif-hint">
              Move at least one slider to enable RUN WHAT-IF.
            </div>
          )}
        </div>
      )}

      {calculating && (
        <div
          role="status"
          className="animate-pulse rounded-sm border border-dashed px-3 py-3 text-xs"
          style={{ borderColor: SIM, color: SIM }}
          data-testid="whatif-calculating"
        >
          CALCULATING… running RUL, Fault, Bearing, Auxiliary and Health Fusion on the perturbed telemetry window. The first run can take a few
          seconds while models load.
        </div>
      )}

      {error && (
        <div role="alert" className="rounded-sm border border-critical bg-criticalBg px-3 py-2 text-xs text-critical" data-testid="whatif-error">
          {error}
        </div>
      )}

      {result && config && !calculating && <WhatIfResults result={result} config={config} stale={stale} />}
    </div>
  );
}
