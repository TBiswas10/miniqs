import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardTitle } from "@/components/ui/card";
import { ResponsiveContainer, LineChart, XAxis, YAxis, Line } from "recharts";

type StrategyRow = {
  strategy: string;
  win_rate: number;
  confidence_avg: number;
  total_pnl: number;
  trend: Array<{ ts: string; pnl: number; confidence: number }>;
};

type Props = {
  rows: StrategyRow[];
  history: Array<{ ts: string; strategy: string; action: string; signal: string; confidence: number; pnl: number; reason: string }>;
  controls: { strategies: Record<string, boolean>; kill_switch: boolean };
  mounted: boolean;
  fmt: (value: number) => string;
};

function strategyStatus(
  strategy: string,
  controls: { strategies: Record<string, boolean>; kill_switch: boolean },
  history: Array<{ strategy: string; reason: string }>,
): "active" | "disabled" | "killed" {
  if (controls.kill_switch) return "killed";
  if (!controls.strategies[strategy]) return "disabled";
  const recentKill = history
    .slice(-20)
    .some((row) => row.strategy === strategy && /kill switch|strategy_kill_switch|killed/i.test(row.reason));
  return recentKill ? "killed" : "active";
}

export function StrategyIntelligencePanel({ rows, history, controls, mounted, fmt }: Props) {
  return (
    <Card className="p-4">
      <CardTitle>Strategy Intelligence Panel</CardTitle>
      <CardBody className="space-y-2">
        {rows.slice(0, 4).map((row) => (
          <div
            key={row.strategy}
            className={`rounded border p-2 ${row.total_pnl < 0 || row.win_rate < 0.4 ? "border-terminal-sell/60 bg-terminal-sell/10" : "border-terminal-border"}`}
          >
            {(() => {
              const recent = history.filter((h) => h.strategy === row.strategy).slice(-8);
              const currentSignal = recent.length ? recent[recent.length - 1].signal : "HOLD";
              const currentConfidence = recent.length ? recent[recent.length - 1].confidence : row.confidence_avg;
              const recentWinRate = recent.length
                ? recent.filter((h) => h.action === "EXECUTED" && h.pnl > 0).length / Math.max(1, recent.filter((h) => h.action === "EXECUTED").length)
                : row.win_rate;
              const status = strategyStatus(row.strategy, controls, history);

              return (
                <>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-sm text-terminal-text">{row.strategy}</span>
                    <div className="flex items-center gap-1">
                      <Badge tone={status === "active" ? "buy" : status === "killed" ? "sell" : "blocked"}>{status}</Badge>
                      <Badge tone={row.total_pnl >= 0 ? "buy" : "sell"}>${fmt(row.total_pnl)}</Badge>
                    </div>
                  </div>
                  <p className="text-[11px] text-terminal-muted">
                    Signal {currentSignal} · Confidence {(currentConfidence * 100).toFixed(1)}% · Recent win {(recentWinRate * 100).toFixed(1)}%
                  </p>
                  <p className="text-[11px] text-terminal-muted">Recent performance: last {Math.max(recent.length, 1)} trades</p>
                </>
              );
            })()}
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[11px] text-terminal-muted">Win rate {(row.win_rate * 100).toFixed(1)}%</span>
              <span className="text-[11px] text-terminal-muted">Avg conf {(row.confidence_avg * 100).toFixed(1)}%</span>
            </div>
            <div className="mt-1 h-[60px] rounded border border-terminal-border bg-black/20 p-1">
              {mounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={row.trend}>
                    <XAxis dataKey="ts" hide />
                    <YAxis hide />
                    <Line dataKey="pnl" stroke="#22c55e" strokeWidth={1.8} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full w-full" />
              )}
            </div>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
