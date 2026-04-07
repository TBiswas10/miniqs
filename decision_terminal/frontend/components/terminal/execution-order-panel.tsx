import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardTitle } from "@/components/ui/card";

type HistoryRow = {
  ts: string;
  action: string;
  strategy: string;
  signal: string;
  confidence: number;
  price: number;
  pnl: number;
  raw: Record<string, unknown>;
};

type Props = {
  pipeline: Record<string, "done" | "blocked" | "idle">;
  history: HistoryRow[];
  openOrders: Array<{ id: string; status: string; symbol: string; price: number }>;
  fmt: (value: number) => string;
};

const lifecycle = ["created", "submitted", "partial", "filled", "canceled", "rejected"] as const;

function extractLifecycle(raw: Record<string, unknown>): string[] {
  const asObj = raw as {
    order_state_path?: unknown;
    execution_result?: { order_state_path?: unknown; order_state?: unknown };
    order_state?: unknown;
  };
  const a = asObj.order_state_path;
  if (Array.isArray(a)) {
    return a.map((v) => String(v).toLowerCase());
  }
  const b = asObj.execution_result?.order_state_path;
  if (Array.isArray(b)) {
    return b.map((v) => String(v).toLowerCase());
  }
  const c = asObj.execution_result?.order_state ?? asObj.order_state;
  if (typeof c === "string" && c.length) {
    return [String(c).toLowerCase()];
  }
  return [];
}

export function ExecutionOrderPanel({ pipeline, history, openOrders, fmt }: Props) {
  const recentExecuted = history.filter((h) => h.action === "EXECUTED").slice(-20).reverse();

  const observed = new Set<string>();
  history.slice(-30).forEach((h) => {
    extractLifecycle(h.raw).forEach((s) => observed.add(s));
  });
  openOrders.forEach((o) => observed.add(String(o.status || "").toLowerCase()));

  return (
    <Card className="p-4">
      <CardTitle>Execution And Order Tracking</CardTitle>
      <CardBody className="space-y-3">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
          {lifecycle.map((step) => {
            const seen = observed.has(step);
            const done = step === "filled" ? pipeline.filled === "done" || seen : seen;
            const tone = done ? "buy" : step === "rejected" || step === "canceled" ? "sell" : "neutral";
            return (
              <div key={step} className="rounded border border-terminal-border px-2 py-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="uppercase tracking-[0.08em] text-terminal-muted">{step}</span>
                  <Badge tone={tone}>{done ? "seen" : "idle"}</Badge>
                </div>
              </div>
            );
          })}
        </div>

        <div className="rounded border border-terminal-border p-2">
          <p className="text-[11px] uppercase tracking-[0.08em] text-terminal-muted">Live Trade Tape</p>
          <div className="mt-2 max-h-[170px] overflow-auto space-y-1 text-xs">
            {recentExecuted.length === 0 ? (
              <p className="text-terminal-muted">No fills yet.</p>
            ) : (
              recentExecuted.map((row, idx) => {
                const exp = Number((row.raw.expected_price as number | undefined) ?? row.price);
                const fill = Number((row.raw.applied_price as number | undefined) ?? (row.raw.filled_price as number | undefined) ?? row.price);
                const slip = fill - exp;
                return (
                  <div key={`${row.ts}-${idx}`} className="flex items-center justify-between rounded border border-terminal-border/70 px-2 py-1">
                    <div>
                      <p className="text-terminal-secondary">{row.ts.slice(11, 19)} {row.strategy} {row.signal}</p>
                      <p className="text-terminal-muted">Fill {fmt(fill)} vs Exp {fmt(exp)} | Slippage {fmt(slip)}</p>
                    </div>
                    <span className={row.pnl >= 0 ? "text-terminal-buy" : "text-terminal-sell"}>${fmt(row.pnl)}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
