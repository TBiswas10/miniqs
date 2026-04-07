import { Badge } from "@/components/ui/badge";
import { DecisionPayload } from "@/lib/types";
import { Play, Square, StepBack, StepForward } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type AdvancedTab = "inspector" | "counterfactual" | "performance" | "replay";

type Props = {
  payload: DecisionPayload;
  advancedTab: AdvancedTab;
  setAdvancedTab: React.Dispatch<React.SetStateAction<AdvancedTab>>;
  selectedDecision: DecisionPayload["history"][number] | null;
  mounted: boolean;
  fmt: (value: number) => string;
  replayMode: boolean;
  setReplayMode: React.Dispatch<React.SetStateAction<boolean>>;
  replayCursor: number;
  replayPlaying: boolean;
  setReplayPlaying: React.Dispatch<React.SetStateAction<boolean>>;
  replayStep: (delta: number) => void;
  activeHistory: DecisionPayload["history"];
};

function toneFromSignal(signal: string) {
  if (signal === "BUY") return "buy" as const;
  if (signal === "SELL") return "sell" as const;
  return "neutral" as const;
}

export function AdvancedPanels({
  payload,
  advancedTab,
  setAdvancedTab,
  selectedDecision,
  mounted,
  fmt,
  replayMode,
  setReplayMode,
  replayCursor,
  replayPlaying,
  setReplayPlaying,
  replayStep,
  activeHistory,
}: Props) {
  return (
    <section className="mb-3 rounded-xl2 border border-terminal-border bg-terminal-panel p-3 shadow-panel">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {([
          ["inspector", "Decision Inspector"],
          ["counterfactual", "Counterfactual Engine"],
          ["performance", "Performance Analytics"],
          ["replay", "Replay System"],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            className={`rounded border px-3 py-1.5 text-xs uppercase tracking-[0.08em] ${advancedTab === id ? "border-terminal-neutral text-terminal-neutral" : "border-terminal-border text-terminal-muted"}`}
            onClick={() => setAdvancedTab(id)}
            title={label}
          >
            {label}
          </button>
        ))}
      </div>

      {advancedTab === "inspector" && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <div className="rounded-md border border-terminal-border bg-black/20 p-3">
            <p className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Decision Inspector</p>
            <p className="mt-1 text-sm text-terminal-secondary">{selectedDecision?.reason ?? payload.decision_inspector.reasoning}</p>
            <pre className="mt-2 max-h-[220px] overflow-auto whitespace-pre-wrap text-xs text-terminal-secondary">
              {JSON.stringify(selectedDecision?.raw ?? payload.decision_inspector.full_object, null, 2)}
            </pre>
          </div>
          <div className="rounded-md border border-terminal-border bg-black/20 p-3">
            <p className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Features + Risk Checks</p>
            <pre className="mt-2 max-h-[100px] overflow-auto whitespace-pre-wrap text-xs text-terminal-secondary">
              {JSON.stringify(payload.decision_inspector.features, null, 2)}
            </pre>
            <div className="mt-2 space-y-1">
              {(selectedDecision?.risk_checks ?? payload.decision_inspector.risk_checks).map((check) => (
                <div key={check.key} className="flex items-center justify-between rounded border border-terminal-border px-2 py-1 text-xs">
                  <span>{check.label}</span>
                  <Badge tone={check.passed ? "buy" : "sell"}>{check.passed ? "PASS" : "FAIL"}</Badge>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {advancedTab === "counterfactual" && (
        <div className="rounded-md border border-terminal-border bg-black/20 p-3">
          <p className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Blocked Trade Simulation</p>
          <div className="mt-2 h-[240px] overflow-auto rounded border border-terminal-border">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-terminal-panel">
                <tr className="border-b border-terminal-border text-terminal-muted">
                  <th className="px-2 py-2">Time</th>
                  <th className="px-2 py-2">Strategy</th>
                  <th className="px-2 py-2">Side</th>
                  <th className="px-2 py-2">Entry</th>
                  <th className="px-2 py-2">Exit</th>
                  <th className="px-2 py-2">Sim PnL</th>
                </tr>
              </thead>
              <tbody>
                {payload.counterfactuals.map((row, idx) => (
                  <tr key={`${row.ts}-${idx}`} className="border-b border-terminal-border/50">
                    <td className="px-2 py-2 text-terminal-muted">{row.ts.slice(11, 19) || row.ts}</td>
                    <td className="px-2 py-2">{row.strategy}</td>
                    <td className="px-2 py-2"><Badge tone={toneFromSignal(row.side)}>{row.side}</Badge></td>
                    <td className="px-2 py-2">{fmt(row.entry_price)}</td>
                    <td className="px-2 py-2">{fmt(row.simulated_exit_price)}</td>
                    <td className={`px-2 py-2 ${row.simulated_pnl >= 0 ? "text-terminal-buy" : "text-terminal-sell"}`}>${fmt(row.simulated_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {advancedTab === "performance" && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <div className="rounded-md border border-terminal-border bg-black/20 p-3">
            <p className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Performance Metrics</p>
            <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded border border-terminal-border p-2" title="Winning trades ratio">
                Win Rate
                <div className="mt-1 text-terminal-neutral">{(payload.performance.win_rate * 100).toFixed(1)}%</div>
              </div>
              <div className="rounded border border-terminal-border p-2" title="Average profit per trade">
                Avg Profit
                <div className="mt-1 text-terminal-neutral">${fmt(payload.performance.avg_profit)}</div>
              </div>
              <div className="rounded border border-terminal-border p-2" title="Maximum drawdown">
                Max Drawdown
                <div className="mt-1 text-terminal-blocked">${fmt(payload.performance.max_drawdown)}</div>
              </div>
              <div className="rounded border border-terminal-border p-2" title="Approximate Sharpe">
                Sharpe (Approx)
                <div className="mt-1 text-terminal-neutral">{payload.performance.sharpe_approx.toFixed(2)}</div>
              </div>
            </div>
          </div>
          <div className="rounded-md border border-terminal-border bg-black/20 p-3">
            <p className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Equity Curve</p>
            <div className="mt-2 h-[220px]">
              {mounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={payload.performance.equity_curve}>
                    <XAxis dataKey="idx" hide />
                    <YAxis hide />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#121821", border: "1px solid #1f2933", color: "#f5f7fa" }}
                      formatter={(v: number) => `$${fmt(Number(v))}`}
                    />
                    <Area type="monotone" dataKey="equity" stroke="#22c55e" fill="#22c55e33" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full w-full" />
              )}
            </div>
          </div>
        </div>
      )}

      {advancedTab === "replay" && (
        <div className="rounded-md border border-terminal-border bg-black/20 p-3">
          <p className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Replay System</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              className={`rounded border px-3 py-1.5 text-xs uppercase tracking-[0.08em] ${replayMode ? "border-terminal-neutral text-terminal-neutral" : "border-terminal-border text-terminal-muted"}`}
              onClick={() => setReplayMode(!replayMode)}
              title="Enable replay mode"
            >
              Replay {replayMode ? "ON" : "OFF"}
            </button>
            <button className="rounded border border-terminal-border p-1.5 text-terminal-secondary" onClick={() => replayStep(-1)} title="Step back">
              <StepBack className="h-4 w-4" />
            </button>
            <button
              className="rounded border border-terminal-border p-1.5 text-terminal-secondary"
              onClick={() => setReplayPlaying((v) => !v)}
              title={replayPlaying ? "Pause" : "Play"}
            >
              {replayPlaying ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <button className="rounded border border-terminal-border p-1.5 text-terminal-secondary" onClick={() => replayStep(1)} title="Step forward">
              <StepForward className="h-4 w-4" />
            </button>
            <span className="text-xs text-terminal-muted">Tick {replayCursor + 1} / {payload.replay.length}</span>
          </div>
          <div className="mt-2 rounded border border-terminal-border p-2 text-xs text-terminal-secondary">
            Pipeline at cursor: {JSON.stringify(activeHistory[Math.min(replayCursor, Math.max(activeHistory.length - 1, 0))]?.raw ?? {}, null, 0)}
          </div>
        </div>
      )}
    </section>
  );
}
