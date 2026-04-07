"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardTitle } from "@/components/ui/card";
import { useDecisionStream } from "@/hooks";
import { AdvancedPanels } from "@/components/terminal/advanced-panels";
import { StrategyIntelligencePanel } from "@/components/terminal/strategy-intelligence-panel";
import { SystemControlPanel } from "@/components/terminal/system-control-panel";
import { CheckCircle2, CircleX, Filter, Info, Radar, ShieldAlert, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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
    controlError,
    clearControlError,
    setTradingEnabled,
    setKillSwitch,
    setStrategyEnabled,
    updateRisk,
  } = useDecisionStream();
  const d = payload.decision;
  const [riskDraft, setRiskDraft] = useState({
    confidence_threshold: payload.meta.controls.risk.confidence_threshold,
    max_position_size: payload.meta.controls.risk.max_position_size,
    max_daily_loss: payload.meta.controls.risk.max_daily_loss,
  });
  const [advancedTab, setAdvancedTab] = useState<"inspector" | "counterfactual" | "performance" | "replay">("inspector");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    setRiskDraft({
      confidence_threshold: payload.meta.controls.risk.confidence_threshold,
      max_position_size: payload.meta.controls.risk.max_position_size,
      max_daily_loss: payload.meta.controls.risk.max_daily_loss,
    });
  }, [
    payload.meta.controls.risk.confidence_threshold,
    payload.meta.controls.risk.max_position_size,
    payload.meta.controls.risk.max_daily_loss,
  ]);

  const confidenceSeries = useMemo(
    () =>
      activeHistory.slice(-20).map((row: { confidence: number }, idx: number) => ({
        idx,
        confidence: Number(row.confidence || 0),
      })),
    [activeHistory],
  );

  const pnlSpark = d.account.pnl_spark || [];
  const streamRows = debugMode ? filteredThoughtStream : filteredThoughtStream.slice(-24);
  const alerts = payload.alerts || [];

  return (
    <main className="min-h-screen bg-terminal-bg px-4 py-4 text-terminal-text md:px-6">
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

      <header className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl2 border border-terminal-border bg-terminal-panel px-4 py-3 shadow-panel">
        <div>
          <h1 className="text-lg font-semibold tracking-[0.02em]">Decision Intelligence Terminal</h1>
          <p className="text-xs text-terminal-muted">Real-time bot cognition and execution diagnostics</p>
        </div>
        <div className="flex items-center gap-2">
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
        <Card className="p-4">
          <CardTitle className="flex items-center gap-2"><Radar className="h-4 w-4" /> Brain Panel</CardTitle>
          <CardBody>
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Signal</p>
                <p className={`text-4xl font-bold ${d.signal.side === "BUY" ? "text-terminal-buy" : d.signal.side === "SELL" ? "text-terminal-sell" : "text-terminal-neutral"}`}>
                  {d.signal.side}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Action</p>
                <p className={`text-3xl font-bold ${d.decision.action === "BLOCKED" ? "text-terminal-blocked" : d.decision.action === "EXECUTE" ? "text-terminal-buy" : "text-terminal-neutral"}`}>
                  {d.decision.action}
                </p>
              </div>
              <Badge tone={toneFromSignal(d.signal.side)}>{d.signal.strategy}</Badge>
              <Badge tone="neutral">{d.signal.timestamp}</Badge>
            </div>

            <div className="mt-4">
              <div className="mb-1 flex items-center justify-between text-xs text-terminal-secondary">
                <span>Confidence</span>
                <span>{(d.signal.confidence * 100).toFixed(1)}%</span>
              </div>
              <div className="h-2 rounded-full bg-terminal-border">
                <div
                  className={`h-2 rounded-full transition-all duration-500 ${d.signal.side === "BUY" ? "bg-terminal-buy" : d.signal.side === "SELL" ? "bg-terminal-sell" : "bg-terminal-neutral"}`}
                  style={{ width: `${Math.min(100, Math.max(0, d.signal.confidence * 100))}%` }}
                />
              </div>
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
            {filteredRiskChecks.slice(-8).map((row, rowIdx) => (
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

        <Card className="p-4">
          <CardTitle className="flex items-center gap-2"><Zap className="h-4 w-4" /> Execution Tracker</CardTitle>
          <CardBody>
            <div className="mb-4 space-y-2">
              {[
                { key: "signal", label: "Signal" },
                { key: "decision", label: "Decision" },
                { key: "sent", label: "Sent" },
                { key: "filled", label: "Filled" },
              ].map((step) => {
                const status = d.decision.pipeline[step.key] ?? "idle";
                const tone = status === "done" ? "bg-terminal-buy" : status === "blocked" ? "bg-terminal-blocked" : "bg-terminal-muted";
                return (
                  <div key={step.key} className="flex items-center justify-between rounded-md border border-terminal-border px-3 py-2" title={`Order stage ${step.label}: ${status}`}>
                    <span className="text-sm">{step.label}</span>
                    <span className={`h-2.5 w-2.5 rounded-full ${tone}`} title={`status: ${status}`} />
                  </div>
                );
              })}
            </div>

            <div className="h-[120px] rounded-md border border-terminal-border bg-black/20 p-2">
              {mounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={confidenceSeries}>
                    <XAxis dataKey="idx" hide />
                    <YAxis domain={[0, 1]} hide />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#121821", border: "1px solid #1f2933", color: "#f5f7fa" }}
                      formatter={(v: number) => `${(Number(v) * 100).toFixed(1)}%`}
                    />
                    <Area type="monotone" dataKey="confidence" stroke="#3b82f6" fill="#3b82f633" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full w-full" />
              )}
            </div>
          </CardBody>
        </Card>
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

        <StrategyIntelligencePanel rows={payload.strategy_intelligence} mounted={mounted} fmt={fmt} />
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
        activeHistory={activeHistory}
      />
    </main>
  );
}
