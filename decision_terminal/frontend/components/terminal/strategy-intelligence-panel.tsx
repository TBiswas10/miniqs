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
            className={`group rounded border p-2 transition-all duration-200 ${row.total_pnl < 0 || row.win_rate < 0.4 ? "border-terminal-sell/60 bg-terminal-sell/10" : "border-terminal-border bg-black/20"} hover:-translate-y-0.5 hover:shadow-neonSoft`}
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
                    <span className="flex items-center gap-2 text-sm text-terminal-text">
                      <span className={`h-2 w-2 rounded-full ${status === "active" ? "bg-terminal-buy animate-softPulse" : status === "killed" ? "bg-terminal-sell" : "bg-terminal-blocked"}`} />
                      {row.strategy}
                    </span>
                    <div className="flex items-center gap-1">
                      <Badge tone={status === "active" ? "buy" : status === "killed" ? "sell" : "blocked"}>{status}</Badge>
                      <Badge tone={row.total_pnl >= 0 ? "buy" : "sell"}>${fmt(row.total_pnl)}</Badge>
                    </div>
                  </div>
                  <p className="text-[11px] text-terminal-muted">
                    Signal {currentSignal} · Confidence {(currentConfidence * 100).toFixed(1)}% · Recent win {(recentWinRate * 100).toFixed(1)}%
                  </p>
                  <p className="text-[11px] text-terminal-muted">Recent performance: last {Math.max(recent.length, 1)} trades</p>
                  <div className="max-h-0 overflow-hidden opacity-0 transition-all duration-200 group-hover:mt-1 group-hover:max-h-16 group-hover:opacity-100">
                    <div className="grid grid-cols-3 gap-1 text-[10px] text-terminal-secondary">
                      <div className="rounded border border-terminal-border/50 px-1 py-1">PnL ${fmt(row.total_pnl)}</div>
                      <div className="rounded border border-terminal-border/50 px-1 py-1">WR {(row.win_rate * 100).toFixed(1)}%</div>
                      <div className="rounded border border-terminal-border/50 px-1 py-1">Conf {(row.confidence_avg * 100).toFixed(1)}%</div>
                    </div>
                  </div>
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
