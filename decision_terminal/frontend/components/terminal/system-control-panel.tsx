import { Card, CardBody, CardTitle } from "@/components/ui/card";
import { RiskControls } from "@/lib/types";
import { Gauge } from "lucide-react";

type Controls = {
  trading_enabled: boolean;
  kill_switch: boolean;
  strategies: Record<string, boolean>;
};

type RiskDraft = Record<string, number>;

type Props = {
  controls: Controls;
  riskDraft: RiskDraft;
  setRiskDraft: React.Dispatch<React.SetStateAction<RiskDraft>>;
  setTradingEnabled: (enabled: boolean) => Promise<unknown>;
  setKillSwitch: (engage: boolean) => Promise<unknown>;
  setStrategyEnabled: (strategy: string, enabled: boolean) => Promise<unknown>;
  updateRisk: (risk: Partial<RiskControls>) => Promise<unknown>;
};

const CORE_RISK_FIELDS = ["confidence_threshold", "max_position_size", "max_daily_loss"] as const;

const RISK_LABELS: Record<string, string> = {
  confidence_threshold: "Confidence",
  max_position_size: "Position Size",
  max_daily_loss: "Daily Loss",
  risk_per_trade: "Risk / Trade",
  daily_loss_limit: "Daily Loss Limit",
  max_exposure: "Max Exposure",
  max_concurrent_positions: "Max Concurrent",
  cooldown_seconds: "Cooldown (sec)",
  max_loss_per_session: "Session Loss Limit",
  portfolio_drawdown_limit: "Portfolio DD Limit",
  per_strategy_drawdown_limit: "Per-Strategy DD",
  extreme_loss_kill_switch: "Extreme Loss Kill",
  strategy_kill_loss: "Strategy Kill Loss",
  vol_target: "Vol Target",
  vol_floor: "Vol Floor",
  vol_ceiling: "Vol Ceiling",
  low_vol_multiplier: "Low Vol Mult",
  high_vol_multiplier: "High Vol Mult",
  min_trade_size: "Min Trade Size",
  max_trade_size: "Max Trade Size",
};

function riskStep(field: string): string {
  if (field.includes("seconds") || field.includes("positions")) return "1";
  if (field.includes("threshold") || field.includes("limit") || field.includes("mult") || field.includes("vol") || field.includes("risk")) return "0.01";
  return "0.1";
}

export function SystemControlPanel({
  controls,
  riskDraft,
  setRiskDraft,
  setTradingEnabled,
  setKillSwitch,
  setStrategyEnabled,
  updateRisk,
}: Props) {
  const advancedRiskFields = Object.keys(riskDraft)
    .filter((key) => !CORE_RISK_FIELDS.includes(key as (typeof CORE_RISK_FIELDS)[number]))
    .sort();

  const renderRiskInput = (field: string) => (
    <label key={field} className="text-xs text-terminal-muted" title={field}>
      {RISK_LABELS[field] ?? field.replace(/_/g, " ")}
      <input
        type="number"
        step={riskStep(field)}
        className="mt-1 w-full rounded border border-terminal-border bg-black/30 px-2 py-1 text-terminal-text"
        value={Number.isFinite(riskDraft[field]) ? riskDraft[field] : 0}
        onChange={(e) => setRiskDraft((prev) => ({ ...prev, [field]: Number(e.target.value) }))}
      />
    </label>
  );

  return (
    <Card className="p-4">
      <CardTitle className="flex items-center gap-2"><Gauge className="h-4 w-4" /> System Control Panel</CardTitle>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <button
            className={`rounded border px-3 py-1.5 text-xs uppercase tracking-[0.08em] ${controls.trading_enabled ? "border-terminal-buy text-terminal-buy" : "border-terminal-border text-terminal-muted"}`}
            onClick={() => void setTradingEnabled(true)}
            title="Resume trading"
          >
            Resume
          </button>
          <button
            className={`rounded border px-3 py-1.5 text-xs uppercase tracking-[0.08em] ${!controls.trading_enabled ? "border-terminal-blocked text-terminal-blocked" : "border-terminal-border text-terminal-muted"}`}
            onClick={() => void setTradingEnabled(false)}
            title="Pause trading"
          >
            Pause
          </button>
          <button
            className={`rounded border px-3 py-1.5 text-xs uppercase tracking-[0.08em] ${controls.kill_switch ? "border-terminal-sell bg-terminal-sell/20 text-terminal-sell" : "border-terminal-border text-terminal-muted"}`}
            onClick={() => void setKillSwitch(!controls.kill_switch)}
            title="Emergency kill switch"
          >
            Kill Switch
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {Object.entries(controls.strategies).map(([strategy, enabled]) => (
            <button
              key={strategy}
              className={`rounded border px-2 py-1 text-xs uppercase tracking-[0.08em] ${enabled ? "border-terminal-buy text-terminal-buy" : "border-terminal-border text-terminal-muted"}`}
              onClick={() => void setStrategyEnabled(strategy, !enabled)}
              title="Toggle strategy"
            >
              {strategy.replace("_", " ")}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-3 gap-2">
          {CORE_RISK_FIELDS.map((field) => renderRiskInput(field))}
        </div>

        <div className="rounded border border-terminal-border p-2">
          <p className="mb-2 text-[11px] uppercase tracking-[0.08em] text-terminal-muted">Advanced Risk Parameters</p>
          <div className="grid grid-cols-2 gap-2 xl:grid-cols-3">
            {advancedRiskFields.map((field) => renderRiskInput(field))}
          </div>
        </div>

        <button
          className="rounded border border-terminal-neutral px-3 py-1.5 text-xs uppercase tracking-[0.08em] text-terminal-neutral"
          onClick={() => void updateRisk(riskDraft)}
          title="Apply risk parameter updates"
        >
          Apply Risk Parameters
        </button>
      </CardBody>
    </Card>
  );
}
