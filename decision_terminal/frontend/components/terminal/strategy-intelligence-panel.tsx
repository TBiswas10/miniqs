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
  mounted: boolean;
  fmt: (value: number) => string;
};

export function StrategyIntelligencePanel({ rows, mounted, fmt }: Props) {
  return (
    <Card className="p-4">
      <CardTitle>Strategy Intelligence Panel</CardTitle>
      <CardBody className="space-y-2">
        {rows.slice(0, 4).map((row) => (
          <div key={row.strategy} className="rounded border border-terminal-border p-2">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-sm text-terminal-text">{row.strategy}</span>
              <Badge tone={row.total_pnl >= 0 ? "buy" : "sell"}>${fmt(row.total_pnl)}</Badge>
            </div>
            <p className="text-[11px] text-terminal-muted">Win rate {(row.win_rate * 100).toFixed(1)}% · Confidence {(row.confidence_avg * 100).toFixed(1)}%</p>
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
