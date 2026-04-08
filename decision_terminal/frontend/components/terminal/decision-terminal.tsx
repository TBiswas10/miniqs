"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardTitle } from "@/components/ui/card";
import { useDecisionStream } from "@/hooks";
import { AdvancedPanels } from "@/components/terminal/advanced-panels";
import { ExecutionOrderPanel } from "@/components/terminal/execution-order-panel";
import { RiskDashboard } from "@/components/terminal/risk-dashboard";
import { StrategyIntelligencePanel } from "@/components/terminal/strategy-intelligence-panel";
import { SystemControlPanel } from "@/components/terminal/system-control-panel";
import { RiskControls } from "@/lib/types";
import { ArrowDownRight, ArrowUpRight, CheckCircle2, ChevronDown, ChevronUp, CircleX, Filter, Info, Radar, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

function toneFromAction(action: string) {
  if (action === "EXECUTE" || action === "EXECUTED") return "buy" as const;
  if (action === "BLOCKED") return "blocked" as const;
  if (action === "HOLD") return "neutral" as const;
  return "muted" as const;
}

function toneFromSignal(signal: string) {
  if (signal === "BUY") return "buy" as const;
  if (signal === "SELL") return "sell" as const;
  return "neutral" as const;
}

function fmt(value: number) {
  if (!Number.isFinite(value)) return "--";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function toRiskDraft(risk: RiskControls): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(risk)) {
    if (typeof value === "number" && Number.isFinite(value)) {
      out[key] = value;
    }
  }
  if (typeof out.confidence_threshold !== "number") out.confidence_threshold = 0.35;
  if (typeof out.max_position_size !== "number") out.max_position_size = 1;
  if (typeof out.max_daily_loss !== "number") out.max_daily_loss = 500;
  return out;
}

export function DecisionTerminal() {
  const {
    payload,
    debugMode,
    setDebugMode,
    filter,
    setFilter,
    filteredThoughtStream,
    logFilter,
    setLogFilter,
    filteredRiskChecks,
    riskFilter,
    setRiskFilter,
    selectedDecision,
    selectedDecisionIndex,
    setSelectedDecisionIndex,
    activeHistory,
    replayMode,
    setReplayMode,
    replayCursor,
    replayPlaying,
    setReplayPlaying,
    replayStep,
    replaySeek,
    controlError,
    clearControlError,
    setTradingEnabled,
    setKillSwitch,
    setStrategyEnabled,
    updateRisk,
  } = useDecisionStream();
  const d = payload.decision;
  const [riskDraft, setRiskDraft] = useState<Record<string, number>>(() => toRiskDraft(payload.meta.controls.risk));
  const [advancedTab, setAdvancedTab] = useState<"inspector" | "counterfactual" | "performance" | "replay">("inspector");
  const [mounted, setMounted] = useState(false);
  const [showAllWhyNotTrade, setShowAllWhyNotTrade] = useState(false);
  const [brainPulse, setBrainPulse] = useState(false);
  const prevTsRef = useRef<string>("");
  const prevConfidenceRef = useRef<{ signal_strength: number; agreement: number; regime_fit: number; historical_edge: number; final: number }>({
    signal_strength: 0,
    agreement: 0,
    regime_fit: 0,
    historical_edge: 0,
    final: 0,
  });

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    setRiskDraft(toRiskDraft(payload.meta.controls.risk));
  }, [payload.meta.controls.risk]);

  useEffect(() => {
    if (!d.signal.timestamp || d.signal.timestamp === "--") return;
    if (prevTsRef.current && prevTsRef.current !== d.signal.timestamp) {
      prevTsRef.current = d.signal.timestamp;
      setBrainPulse(true);
      const id = window.setTimeout(() => setBrainPulse(false), 420);
      return () => window.clearTimeout(id);
    }
    prevTsRef.current = d.signal.timestamp;
    return undefined;
  }, [d.signal.timestamp]);

  const equityCurve = useMemo(() => payload.performance.equity_curve || [], [payload.performance.equity_curve]);

  const drawdownSeries = useMemo(() => {
    let peak = Number.NEGATIVE_INFINITY;
    return equityCurve.map((row) => {
      const eq = Number(row.equity || 0);
      peak = Math.max(peak, eq);
      return {
        idx: row.idx,
        drawdown: peak > 0 ? peak - eq : 0,
      };
    });
  }, [equityCurve]);

  const rollingMetrics = useMemo(() => {
    const rows = activeHistory.slice(-30);
    if (rows.length < 3) {
      return { sharpe: 0, volatility: 0, winRate: payload.performance.win_rate };
    }
    const pnls = rows.map((r) => Number(r.pnl || 0));
    const deltas: number[] = [];
    for (let i = 1; i < pnls.length; i += 1) {
      deltas.push(pnls[i] - pnls[i - 1]);
    }
    const mean = deltas.reduce((acc, v) => acc + v, 0) / Math.max(deltas.length, 1);
    const variance = deltas.reduce((acc, v) => acc + (v - mean) ** 2, 0) / Math.max(deltas.length, 1);
    const sigma = Math.sqrt(variance);
    const sharpe = sigma > 0 ? (mean / sigma) * Math.sqrt(deltas.length) : 0;
    const wins = deltas.filter((v) => v > 0).length;
    return {
      sharpe,
      volatility: sigma,
      winRate: wins / Math.max(deltas.length, 1),
    };
  }, [activeHistory, payload.performance.win_rate]);

  const strategyPnlBreakdown = useMemo(
    () =>
      payload.strategy_intelligence
        .slice(0, 5)
        .map((row) => ({ strategy: row.strategy.replace("_", " "), pnl: Number(row.total_pnl || 0) })),
    [payload.strategy_intelligence],
  );

  const recentRiskFailures = useMemo(
    () =>
      payload.why_not_trade
        .slice(-30)
        .filter((row) => row.checks.some((check) => !check.passed)).length,
    [payload.why_not_trade],
  );
  const visibleRiskRows = useMemo(
    () => (showAllWhyNotTrade ? filteredRiskChecks : filteredRiskChecks.slice(0, 3)),
    [filteredRiskChecks, showAllWhyNotTrade],
  );

  const pnlSpark = d.account.pnl_spark || [];
  const finalConfidence = Number(d.signal.confidence?.final ?? 0);
  const confidenceParts = d.signal.confidence;
  const confidenceTrend = {
    signal_strength: Number(confidenceParts.signal_strength ?? 0) - Number(prevConfidenceRef.current.signal_strength ?? 0),
    agreement: Number(confidenceParts.agreement ?? 0) - Number(prevConfidenceRef.current.agreement ?? 0),
    regime_fit: Number(confidenceParts.regime_fit ?? 0) - Number(prevConfidenceRef.current.regime_fit ?? 0),
    historical_edge: Number(confidenceParts.historical_edge ?? 0) - Number(prevConfidenceRef.current.historical_edge ?? 0),
  };
  useEffect(() => {
    prevConfidenceRef.current = {
      signal_strength: Number(confidenceParts.signal_strength ?? 0),
      agreement: Number(confidenceParts.agreement ?? 0),
      regime_fit: Number(confidenceParts.regime_fit ?? 0),
      historical_edge: Number(confidenceParts.historical_edge ?? 0),
      final: Number(confidenceParts.final ?? 0),
    };
  }, [confidenceParts]);
  const strategyHealthRows = Object.entries(payload.strategy_health || {}).sort((a, b) => Number(b[1]?.health_score ?? 0) - Number(a[1]?.health_score ?? 0));
  const riskDebug = payload.risk_debug;
  const streamRows = debugMode ? filteredThoughtStream : filteredThoughtStream.slice(-24);
  const alerts = payload.alerts || [];

  return (
    <main className={`min-h-screen bg-terminal-bg px-4 py-4 text-terminal-text md:px-6 ${replayMode ? "replay-tint" : ""}`}>
      <div className="mb-2 space-y-1">
        {alerts.map((alert, idx) => (
          <div
            key={`${alert.level}-${idx}`}
            className={`rounded-md border px-3 py-2 text-xs ${alert.level === "error" ? "border-terminal-sell/50 bg-terminal-sell/10 text-terminal-sell" : alert.level === "warn" ? "border-terminal-blocked/50 bg-terminal-blocked/10 text-terminal-blocked" : "border-terminal-neutral/50 bg-terminal-neutral/10 text-terminal-neutral"}`}
            title="System alert"
          >
            {alert.message}
          </div>
        ))}
        {controlError ? (
          <div className="flex items-center justify-between rounded-md border border-terminal-sell/50 bg-terminal-sell/10 px-3 py-2 text-xs text-terminal-sell">
            <span>Control action failed: {controlError}</span>
            <button
              className="rounded border border-terminal-sell/40 px-2 py-1 text-[10px] uppercase tracking-[0.08em]"
              onClick={clearControlError}
              title="Dismiss control error"
            >
              Dismiss
            </button>
          </div>
        ) : null}
      </div>

      <header className="topbar-glass mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl2 px-4 py-3 shadow-panel">
        <div>
          <h1 className="text-lg font-semibold tracking-[0.02em]">Decision Intelligence Terminal</h1>
          <p className="text-xs text-terminal-muted">Real-time bot cognition and execution diagnostics</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded border border-terminal-border/70 bg-black/20 px-2 py-1 text-[10px] uppercase tracking-[0.08em] text-terminal-muted">
            Last updated {payload.meta.last_tick_age_sec == null ? "--" : `${Math.round(payload.meta.last_tick_age_sec * 1000)} ms ago`}
          </span>
          {replayMode ? <Badge tone="neutral" className="animate-softPulse">REPLAY MODE</Badge> : null}
          <Badge tone={payload.meta.connected ? "buy" : "blocked"}>{payload.meta.connection_event}</Badge>
          <button
            className="rounded-md border border-terminal-border px-3 py-1.5 text-xs uppercase tracking-[0.08em] text-terminal-secondary transition hover:border-terminal-neutral"
            onClick={() => setDebugMode((v) => !v)}
            title="Toggle expanded thought stream"
          >
            Debug {debugMode ? "ON" : "OFF"}
          </button>
          <div className="flex items-center rounded-md border border-terminal-border p-0.5">
            {(["all", "executed", "blocked"] as const).map((k) => (
              <button
                key={k}
                className={`rounded px-2 py-1 text-xs uppercase tracking-[0.08em] ${filter === k ? "bg-terminal-neutral/20 text-terminal-neutral" : "text-terminal-muted"}`}
                onClick={() => setFilter(k)}
                title="Filter decision history"
              >
                {k}
              </button>
            ))}
          </div>
        </div>
      </header>

      <section className="terminal-grid mb-3">
        <Card className={`p-4 ${brainPulse ? "tick-pulse" : ""}`}>
          <CardTitle className="flex items-center gap-2"><Radar className="h-4 w-4" /> Brain Panel</CardTitle>
          <CardBody>
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Signal</p>
                <p className={`glow-number text-5xl font-bold ${d.signal.side === "BUY" ? "text-terminal-buy" : d.signal.side === "SELL" ? "text-terminal-sell" : "text-terminal-neutral"}`}>
                  {d.signal.side}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Action</p>
                <p className={`fade-slide glow-number text-4xl font-bold ${d.decision.action === "BLOCKED" ? "text-terminal-blocked" : d.decision.action === "EXECUTE" ? "text-terminal-buy" : "text-terminal-neutral"}`}>
                  {d.decision.action}
                </p>
              </div>
              <Badge tone={toneFromSignal(d.signal.side)}>{d.signal.strategy}</Badge>
              <Badge tone="neutral">{d.signal.timestamp}</Badge>
            </div>

            <div className="mt-4">
              <div className="mb-1 flex items-center justify-between text-xs text-terminal-secondary">
                <span>Confidence</span>
                <span>{(finalConfidence * 100).toFixed(1)}%</span>
              </div>
              <div className="relative h-2.5 overflow-hidden rounded-full bg-terminal-border/70">
                <div
                  className={`h-2.5 rounded-full transition-all duration-500 ${d.signal.side === "BUY" ? "bg-gradient-to-r from-terminal-buy/70 to-terminal-buy" : d.signal.side === "SELL" ? "bg-gradient-to-r from-terminal-sell/65 to-terminal-sell" : "bg-gradient-to-r from-terminal-neutral/65 to-terminal-neutral"}`}
                  style={{ width: `${Math.min(100, Math.max(0, finalConfidence * 100))}%` }}
                />
                <div className="pointer-events-none absolute inset-y-0 w-10 bg-gradient-to-r from-transparent via-white/30 to-transparent opacity-35 animate-shimmer" />
              </div>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] md:grid-cols-4">
              {([
                ["Signal", Number(confidenceParts.signal_strength ?? 0), confidenceTrend.signal_strength],
                ["Agreement", Number(confidenceParts.agreement ?? 0), confidenceTrend.agreement],
                ["Regime", Number(confidenceParts.regime_fit ?? 0), confidenceTrend.regime_fit],
                ["Edge", Number(confidenceParts.historical_edge ?? 0), confidenceTrend.historical_edge],
              ] as const).map(([label, value, trend]) => (
                <div key={label} className="rounded border border-terminal-border/70 bg-black/20 px-2 py-2">
                  <p className="uppercase tracking-[0.08em] text-terminal-muted">{label}</p>
                  <p className="mt-1 flex items-center gap-1 text-terminal-secondary">
                    <span>{Math.round(value * 100)}%</span>
                    {trend >= 0 ? <ArrowUpRight className="h-3 w-3 text-terminal-buy" /> : <ArrowDownRight className="h-3 w-3 text-terminal-sell" />}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-3 h-[70px] rounded-md border border-terminal-border bg-black/20 p-2" title="Recent signal confidence trend">
              {mounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={d.signal.trend || []}>
                    <XAxis dataKey="idx" hide />
                    <YAxis domain={[0, 1]} hide />
                    <Line dataKey="confidence" stroke="#94a3b8" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full w-full" />
              )}
            </div>

            <p className="mt-4 rounded-md border border-terminal-border bg-black/20 px-3 py-2 text-sm text-terminal-secondary">{d.decision.reason}</p>
          </CardBody>
        </Card>

        <Card className="p-4">
          <CardTitle className="flex items-center gap-2"><ShieldAlert className="h-4 w-4" /> Why Not Trade</CardTitle>
          <div className="mt-2 flex items-center gap-1">
            {(["all", "failed", "executed"] as const).map((k) => (
              <button
                key={k}
                className={`rounded border px-2 py-1 text-[10px] uppercase tracking-[0.08em] ${riskFilter === k ? "border-terminal-neutral text-terminal-neutral" : "border-terminal-border text-terminal-muted"}`}
                onClick={() => setRiskFilter(k)}
                title="Filter risk checks"
              >
                {k}
              </button>
            ))}
          </div>
          <CardBody className="space-y-2">
            {(payload.hold_reasons || []).map((reason, idx) => (
              <div key={`${reason.reason}-${idx}`} className="fade-slide rounded border border-terminal-border/70 bg-black/20 px-3 py-2">
                <div className="mb-1 flex items-center justify-between text-[11px]">
                  <span className="text-terminal-secondary">{reason.reason}</span>
                  <span className="text-terminal-muted">{Math.round(Number(reason.impact || 0) * 100)}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-terminal-border/70">
                  <div
                    className="h-2 rounded-full bg-gradient-to-r from-terminal-sell/55 via-terminal-sell/75 to-terminal-sell transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(0, Number(reason.impact || 0) * 100))}%` }}
                  />
                </div>
              </div>
            ))}
            {visibleRiskRows.map((row, rowIdx) => (
              <div key={`${row.ts}-${rowIdx}`} className="rounded-md border border-terminal-border px-3 py-2">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.08em] text-terminal-muted">{row.ts}</p>
                  <p className="text-xs text-terminal-secondary">{row.reason}</p>
                </div>
                <div className="mt-2 space-y-1">
                  {row.checks.map((check) => (
                    <div key={`${row.ts}-${check.key}`} className="flex items-start justify-between rounded border border-terminal-border/60 px-2 py-1">
                      <div>
                        <p className="text-xs text-terminal-text">{check.label}</p>
                        <p className="text-[11px] text-terminal-muted">{check.reason}</p>
                      </div>
                      <div title={check.passed ? "Check passed" : "Check failed"}>
                        {check.passed ? <CheckCircle2 className="h-4 w-4 text-terminal-buy" /> : <CircleX className="h-4 w-4 text-terminal-sell" />}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {filteredRiskChecks.length > 3 ? (
              <button
                className="mt-1 inline-flex items-center gap-1 rounded border border-terminal-border px-2 py-1 text-[11px] text-terminal-secondary transition hover:border-terminal-neutral hover:text-terminal-neutral"
                onClick={() => setShowAllWhyNotTrade((v) => !v)}
                aria-expanded={showAllWhyNotTrade}
                title={showAllWhyNotTrade ? "Collapse Why Not Trade list" : "Expand Why Not Trade list"}
              >
                {showAllWhyNotTrade ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                <span>{showAllWhyNotTrade ? "Show less" : `Expand more (${filteredRiskChecks.length - 3} more)`}</span>
              </button>
            ) : null}
          </CardBody>
        </Card>
      </section>

      <section className="mb-3 grid grid-cols-1 gap-3 2xl:grid-cols-3">
        <Card className="p-4 2xl:col-span-2">
          <CardTitle>Portfolio Live Analytics</CardTitle>
          <CardBody className="space-y-3">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4 text-xs">
              <div className="rounded border border-terminal-border p-2">
                Rolling Sharpe
                <div className="mt-1 text-terminal-neutral">{rollingMetrics.sharpe.toFixed(2)}</div>
              </div>
              <div className="rounded border border-terminal-border p-2">
                Rolling Volatility
                <div className="mt-1 text-terminal-neutral">{rollingMetrics.volatility.toFixed(2)}</div>
              </div>
              <div className="rounded border border-terminal-border p-2">
                Rolling Win Rate
                <div className="mt-1 text-terminal-neutral">{(rollingMetrics.winRate * 100).toFixed(1)}%</div>
              </div>
              <div className="rounded border border-terminal-border p-2">
                Max Drawdown
                <div className="mt-1 text-terminal-blocked">${fmt(payload.performance.max_drawdown)}</div>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              <div className="h-[170px] rounded border border-terminal-border bg-black/20 p-2">
                {mounted ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={equityCurve}>
                      <XAxis dataKey="idx" hide />
                      <YAxis hide />
                      <Tooltip formatter={(v: number) => `$${fmt(Number(v))}`} />
                      <Area type="monotone" dataKey="equity" stroke="#22c55e" fill="#22c55e33" />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full w-full" />
                )}
              </div>
              <div className="h-[170px] rounded border border-terminal-border bg-black/20 p-2">
                {mounted ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={drawdownSeries}>
                      <XAxis dataKey="idx" hide />
                      <YAxis hide />
                      <Tooltip formatter={(v: number) => `$${fmt(Number(v))}`} />
                      <Line type="monotone" dataKey="drawdown" stroke="#f59e0b" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full w-full" />
                )}
              </div>
            </div>
          </CardBody>
        </Card>

        <Card className="p-4">
          <CardTitle>Per-Strategy PnL</CardTitle>
          <CardBody>
            <div className="h-[250px] rounded border border-terminal-border bg-black/20 p-2">
              {mounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={strategyPnlBreakdown}>
                    <XAxis dataKey="strategy" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                    <YAxis hide />
                    <Tooltip formatter={(v: number) => `$${fmt(Number(v))}`} />
                    <Bar dataKey="pnl" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full w-full" />
              )}
            </div>
          </CardBody>
        </Card>
      </section>

      <section className="mb-3">
        <Card className="p-4">
          <CardTitle className="flex items-center gap-2"><Info className="h-4 w-4" /> Thought Stream</CardTitle>
          <div className="mt-2 flex items-center gap-1">
            {(["all", "errors", "strategies", "blocked"] as const).map((k) => (
              <button
                key={k}
                className={`rounded border px-2 py-1 text-[10px] uppercase tracking-[0.08em] ${logFilter === k ? "border-terminal-neutral text-terminal-neutral" : "border-terminal-border text-terminal-muted"}`}
                onClick={() => setLogFilter(k)}
                title="Filter thought stream"
              >
                {k}
              </button>
            ))}
          </div>
          <CardBody>
            <div className="h-[250px] overflow-y-auto rounded-md border border-terminal-border bg-black/30 p-3 font-mono text-xs">
              {streamRows.map((row, idx) => (
                <div
                  key={`${row.ts}-${idx}`}
                  className={`mb-1 flex gap-2 rounded px-2 py-1 transition-colors ${row.level === "error" ? "text-terminal-sell" : row.level === "warn" ? "text-terminal-blocked" : "text-terminal-secondary"}`}
                >
                  <span className="w-28 text-terminal-muted">{row.ts.slice(11, 19) || row.ts}</span>
                  <span className="w-28 uppercase">{row.stage}</span>
                  <span className="flex-1">{row.message}</span>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      </section>

      <section className="bottom-grid pb-2">
        <Card className="p-4">
          <CardTitle className="flex items-center gap-2"><Filter className="h-4 w-4" /> Decision History</CardTitle>
          <CardBody>
            <div className="h-[280px] overflow-auto rounded-md border border-terminal-border">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-terminal-panel">
                  <tr className="border-b border-terminal-border text-terminal-muted">
                    <th className="px-2 py-2 font-medium">Time</th>
                    <th className="px-2 py-2 font-medium">Signal</th>
                    <th className="px-2 py-2 font-medium">Action</th>
                    <th className="px-2 py-2 font-medium">Strategy</th>
                    <th className="px-2 py-2 font-medium">Conf.</th>
                    <th className="px-2 py-2 font-medium">PnL</th>
                    <th className="px-2 py-2 font-medium">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {activeHistory.map((row, idx) => (
                    <tr
                      key={`${row.ts}-${idx}`}
                      className={`cursor-pointer border-b border-terminal-border/50 transition hover:bg-terminal-neutral/10 ${selectedDecisionIndex === idx ? "bg-terminal-neutral/15" : ""}`}
                      onClick={() => setSelectedDecisionIndex(idx)}
                      title="Open in decision inspector"
                    >
                      <td className="px-2 py-2 text-terminal-muted">{row.ts.slice(11, 19) || row.ts}</td>
                      <td className="px-2 py-2">
                        <Badge tone={toneFromSignal(row.signal)}>{row.signal}</Badge>
                      </td>
                      <td className="px-2 py-2">
                        <Badge tone={toneFromAction(row.action)}>{row.action}</Badge>
                      </td>
                      <td className="px-2 py-2 text-terminal-secondary">{row.strategy}</td>
                      <td className="px-2 py-2">{(Number(row.confidence) * 100).toFixed(1)}%</td>
                      <td className={`px-2 py-2 ${Number(row.pnl) >= 0 ? "text-terminal-buy" : "text-terminal-sell"}`}>${fmt(Number(row.pnl))}</td>
                      <td className="px-2 py-2 text-terminal-secondary" title={row.reason}>{row.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>

        <Card className="p-4">
          <CardTitle>State Panel</CardTitle>
          <CardBody className="space-y-2">
            <div className="rounded-md border border-terminal-border p-3">
              <p className="text-xs uppercase text-terminal-muted">Position</p>
              <p className="mt-1 text-lg font-semibold">{d.position.symbol}</p>
              <p className="text-sm text-terminal-secondary">size {fmt(d.position.size)} @ {fmt(d.position.price)}</p>
            </div>
            <div className="rounded-md border border-terminal-border p-3">
              <p className="text-xs uppercase text-terminal-muted">Cash</p>
              <p className="mt-1 text-lg font-semibold">${fmt(d.account.cash)}</p>
            </div>
            <div className="rounded-md border border-terminal-border p-3">
              <p className="text-xs uppercase text-terminal-muted">PnL</p>
              <p className={`mt-1 text-lg font-semibold ${d.account.pnl >= 0 ? "text-terminal-buy" : "text-terminal-sell"}`}>${fmt(d.account.pnl)}</p>
            </div>
            <div className="rounded-md border border-terminal-border p-3">
              <p className="text-xs uppercase text-terminal-muted">Open Orders</p>
              <p className="mt-1 text-sm text-terminal-secondary">{d.account.open_orders.length}</p>
            </div>
            <div className="h-[90px] rounded-md border border-terminal-border bg-black/20 p-2" title="PnL sparkline">
              {mounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={pnlSpark}>
                    <XAxis dataKey="idx" hide />
                    <YAxis hide />
                    <Line dataKey="pnl" stroke="#38bdf8" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full w-full" />
              )}
            </div>
          </CardBody>
        </Card>

        <ExecutionOrderPanel
          pipeline={d.decision.pipeline}
          history={activeHistory}
          openOrders={d.account.open_orders}
          fmt={fmt}
        />
      </section>

      <section className="mb-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <SystemControlPanel
          controls={payload.meta.controls}
          riskDraft={riskDraft}
          setRiskDraft={setRiskDraft}
          setTradingEnabled={setTradingEnabled}
          setKillSwitch={setKillSwitch}
          setStrategyEnabled={setStrategyEnabled}
          updateRisk={updateRisk}
        />

        <StrategyIntelligencePanel
          rows={payload.strategy_intelligence}
          history={activeHistory}
          controls={{ strategies: payload.meta.controls.strategies, kill_switch: payload.meta.controls.kill_switch }}
          mounted={mounted}
          fmt={fmt}
        />
      </section>

      <section className="mb-3">
        <RiskDashboard
          symbol={d.position.symbol}
          positionSize={d.position.size}
          price={d.position.price}
          maxPositionSize={payload.meta.controls.risk.max_position_size}
          confidenceThreshold={payload.meta.controls.risk.confidence_threshold}
          maxDrawdown={payload.performance.max_drawdown}
          alerts={payload.alerts}
          recentRiskFailures={recentRiskFailures}
          killSwitch={payload.meta.controls.kill_switch}
          riskState={payload.risk_state}
          fmt={fmt}
        />
      </section>

      <section className="mb-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Card className="p-4">
          <CardTitle>Strategy Health</CardTitle>
          <CardBody className="space-y-2">
            {strategyHealthRows.length === 0 ? (
              <div className="rounded border border-terminal-border px-3 py-2 text-xs text-terminal-muted">No strategy health data yet.</div>
            ) : (
              strategyHealthRows.map(([name, row]) => {
                const health = Number(row?.health_score ?? 0);
                const status = String(row?.status ?? "inactive");
                const statusTone = status === "healthy" ? "buy" : status === "degrading" ? "blocked" : "neutral";
                return (
                  <div key={name} className="rounded border border-terminal-border px-3 py-2 transition hover:border-terminal-neutral/50 hover:shadow-neonSoft">
                    <div className="mb-2 flex items-center justify-between">
                      <p className="text-sm text-terminal-text">{name.replaceAll("_", " ")}</p>
                      <Badge tone={statusTone}>{status}</Badge>
                    </div>
                    <div className="mb-2 h-2 rounded-full bg-terminal-border">
                      <div
                        className={`h-2 rounded-full transition-all duration-500 ${health >= 0.6 ? "bg-terminal-buy" : health >= 0.35 ? "bg-terminal-blocked" : "bg-terminal-neutral"}`}
                        style={{ width: `${Math.min(100, Math.max(0, health * 100))}%` }}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-[11px] text-terminal-secondary md:grid-cols-4">
                      <div>Health {Math.round(health * 100)}%</div>
                      <div>Part {(Number(row?.participation_rate ?? 0) * 100).toFixed(1)}%</div>
                      <div>Hit {(Number(row?.recent_hit_rate ?? 0) * 100).toFixed(1)}%</div>
                      <div>Edge {(Number(row?.contribution_score ?? 0) * 100).toFixed(1)}%</div>
                    </div>
                  </div>
                );
              })
            )}
          </CardBody>
        </Card>

        <Card className="p-4">
          <CardTitle>Risk Gate Debugger</CardTitle>
          <CardBody className="space-y-2">
            {[
              { key: "confidence_gate", label: "Confidence Gate", value: Number(riskDebug?.confidence_gate?.value ?? 0), threshold: Number(riskDebug?.confidence_gate?.threshold ?? 0), passed: Boolean(riskDebug?.confidence_gate?.passed), delta: Number(riskDebug?.confidence_gate?.delta ?? 0) },
              { key: "position_limit", label: "Position Limit", value: Number(riskDebug?.position_limit?.current ?? 0), threshold: Number(riskDebug?.position_limit?.max ?? 0), passed: Boolean(riskDebug?.position_limit?.passed), delta: Number(riskDebug?.position_limit?.delta ?? 0) },
              { key: "drawdown_guard", label: "Drawdown Guard", value: Number(riskDebug?.drawdown_guard?.current_dd ?? 0), threshold: Number(riskDebug?.drawdown_guard?.max_dd ?? 0), passed: Boolean(riskDebug?.drawdown_guard?.passed), delta: Number(riskDebug?.drawdown_guard?.delta ?? 0) },
            ].map((gate) => (
              <div key={gate.key} className="rounded border border-terminal-border px-3 py-2">
                <div className="mb-1 flex items-center justify-between">
                  <p className="text-sm text-terminal-text">{gate.label}</p>
                  <div title={gate.passed ? "Gate passed" : "Gate failed"}>
                    {gate.passed ? <CheckCircle2 className="h-4 w-4 text-terminal-buy" /> : <CircleX className="h-4 w-4 text-terminal-sell" />}
                  </div>
                </div>
                {(() => {
                  const barMax = Math.max(gate.value, gate.threshold, 1e-9);
                  const valuePct = (gate.value / barMax) * 100;
                  const thresholdPct = (gate.threshold / barMax) * 100;
                  return (
                    <div className="relative mt-2 h-2.5 rounded-full bg-terminal-border/75">
                      <div className={`h-2.5 rounded-full transition-all duration-500 ${gate.passed ? "bg-gradient-to-r from-terminal-buy/60 to-terminal-buy" : "bg-gradient-to-r from-terminal-sell/60 to-terminal-sell"}`} style={{ width: `${Math.min(100, Math.max(0, valuePct))}%` }} />
                      <div className="absolute inset-y-0 w-[2px] bg-terminal-blocked/85" style={{ left: `${Math.min(100, Math.max(0, thresholdPct))}%` }} />
                    </div>
                  );
                })()}
                <div className="text-[11px] text-terminal-secondary">
                  <p>value {fmt(gate.value)} / threshold {fmt(gate.threshold)}</p>
                  <p className={gate.delta >= 0 ? "text-terminal-buy" : "text-terminal-sell"}>delta {fmt(gate.delta)}</p>
                </div>
              </div>
            ))}
            <div className="rounded border border-terminal-border px-3 py-2 text-[11px] text-terminal-muted">
              Hold blockers: {(payload.hold_reasons || []).map((r) => `${r.reason} (${Math.round(Number(r.impact || 0) * 100)}%)`).join(", ") || "none"}
            </div>
          </CardBody>
        </Card>
      </section>

      <AdvancedPanels
        payload={payload}
        advancedTab={advancedTab}
        setAdvancedTab={setAdvancedTab}
        selectedDecision={selectedDecision}
        mounted={mounted}
        fmt={fmt}
        replayMode={replayMode}
        setReplayMode={setReplayMode}
        replayCursor={replayCursor}
        replayPlaying={replayPlaying}
        setReplayPlaying={setReplayPlaying}
        replayStep={replayStep}
        replaySeek={replaySeek}
        activeHistory={activeHistory}
      />
    </main>
  );
}
