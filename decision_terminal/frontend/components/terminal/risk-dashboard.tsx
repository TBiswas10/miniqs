import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardTitle } from "@/components/ui/card";

type Props = {
  symbol: string;
  positionSize: number;
  price: number;
  maxPositionSize: number;
  confidenceThreshold: number;
  maxDrawdown: number;
  alerts: Array<{ level: "info" | "warn" | "error"; message: string }>;
  recentRiskFailures: number;
  killSwitch: boolean;
  riskState?: {
    halted: boolean;
    kill_switch: boolean;
    trading_enabled: boolean;
    latest_risk_type: string;
    latest_risk_reason: string;
    latest_risk_severity: string;
  };
  fmt: (value: number) => string;
};

function riskStatus(
  maxDrawdown: number,
  recentRiskFailures: number,
  hasErrorAlert: boolean,
  killSwitch: boolean,
): "safe" | "warning" | "critical" {
  if (killSwitch || hasErrorAlert || maxDrawdown > 120 || recentRiskFailures >= 8) return "critical";
  if (maxDrawdown > 60 || recentRiskFailures >= 4) return "warning";
  return "safe";
}

export function RiskDashboard({
  symbol,
  positionSize,
  price,
  maxPositionSize,
  confidenceThreshold,
  maxDrawdown,
  alerts,
  recentRiskFailures,
  killSwitch,
  riskState,
  fmt,
}: Props) {
  const liveRiskState = riskState ?? {
    halted: false,
    kill_switch: false,
    trading_enabled: true,
    latest_risk_type: "",
    latest_risk_reason: "",
    latest_risk_severity: "info",
  };
  const notional = positionSize * price;
  const utilization = maxPositionSize > 0 ? Math.min(1, Math.abs(positionSize) / maxPositionSize) : 0;
  const status = riskStatus(maxDrawdown, recentRiskFailures, alerts.some((a) => a.level === "error"), killSwitch);

  return (
    <Card className="p-4">
      <CardTitle>Risk Dashboard</CardTitle>
      <CardBody className="space-y-3">
        <div className="flex items-center justify-between rounded border border-terminal-border px-3 py-2">
          <span className="text-xs uppercase tracking-[0.08em] text-terminal-muted">Risk Status</span>
          <Badge tone={status === "safe" ? "buy" : status === "warning" ? "blocked" : "sell"}>{status}</Badge>
        </div>

        <div className="rounded border border-terminal-border p-2">
          <p className="text-[11px] uppercase tracking-[0.08em] text-terminal-muted">Live Risk State</p>
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-terminal-muted">Trading</span>
              <div className={liveRiskState.trading_enabled && !liveRiskState.kill_switch ? "text-terminal-buy" : "text-terminal-sell"}>
                {liveRiskState.trading_enabled && !liveRiskState.kill_switch ? "Enabled" : "Paused"}
              </div>
            </div>
            <div>
              <span className="text-terminal-muted">Halted</span>
              <div className={liveRiskState.halted ? "text-terminal-sell" : "text-terminal-buy"}>{liveRiskState.halted ? "Yes" : "No"}</div>
            </div>
            <div className="col-span-2">
              <span className="text-terminal-muted">Latest Risk</span>
              <div className="text-terminal-secondary">
                {liveRiskState.latest_risk_type ? `${liveRiskState.latest_risk_type}: ${liveRiskState.latest_risk_reason || "no reason provided"}` : "Monitoring for risk events"}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded border border-terminal-border p-2">
            <p className="text-terminal-muted">Exposure ({symbol})</p>
            <p className="mt-1 text-terminal-secondary">{fmt(positionSize)} units</p>
            <p className="text-terminal-secondary">${fmt(notional)} notional</p>
          </div>
          <div className="rounded border border-terminal-border p-2">
            <p className="text-terminal-muted">Vol-Scaled Position</p>
            <p className="mt-1 text-terminal-secondary">Limit {fmt(maxPositionSize)}</p>
            <p className="text-terminal-secondary">Utilization {(utilization * 100).toFixed(1)}%</p>
          </div>
          <div className="rounded border border-terminal-border p-2">
            <p className="text-terminal-muted">Portfolio Drawdown</p>
            <p className="mt-1 text-terminal-blocked">${fmt(maxDrawdown)}</p>
          </div>
          <div className="rounded border border-terminal-border p-2">
            <p className="text-terminal-muted">Confidence Gate</p>
            <p className="mt-1 text-terminal-secondary">{(confidenceThreshold * 100).toFixed(1)}%</p>
          </div>
        </div>

        <div className="rounded border border-terminal-border p-2">
          <p className="text-[11px] uppercase tracking-[0.08em] text-terminal-muted">Risk Alerts</p>
          <div className="mt-2 space-y-1 text-xs">
            {alerts.length === 0 ? <p className="text-terminal-muted">No active risk alerts</p> : null}
            {alerts.slice(-4).map((alert, idx) => (
              <p
                key={`${alert.level}-${idx}`}
                className={alert.level === "error" ? "text-terminal-sell" : alert.level === "warn" ? "text-terminal-blocked" : "text-terminal-secondary"}
              >
                {alert.message}
              </p>
            ))}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
