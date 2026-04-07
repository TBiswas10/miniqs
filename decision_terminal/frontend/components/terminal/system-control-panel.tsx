import { Card, CardBody, CardTitle } from "@/components/ui/card";
import { Gauge } from "lucide-react";

type Controls = {
  trading_enabled: boolean;
  kill_switch: boolean;
  strategies: Record<string, boolean>;
};

type RiskDraft = {
  confidence_threshold: number;
  max_position_size: number;
  max_daily_loss: number;
};

type Props = {
  controls: Controls;
  riskDraft: RiskDraft;
  setRiskDraft: React.Dispatch<React.SetStateAction<RiskDraft>>;
  setTradingEnabled: (enabled: boolean) => Promise<unknown>;
  setKillSwitch: (engage: boolean) => Promise<unknown>;
  setStrategyEnabled: (strategy: string, enabled: boolean) => Promise<unknown>;
  updateRisk: (risk: RiskDraft) => Promise<unknown>;
};

export function SystemControlPanel({
  controls,
  riskDraft,
  setRiskDraft,
  setTradingEnabled,
  setKillSwitch,
  setStrategyEnabled,
  updateRisk,
}: Props) {
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
          <label className="text-xs text-terminal-muted" title="Confidence threshold">
            Confidence
            <input
              type="number"
              step="0.01"
              className="mt-1 w-full rounded border border-terminal-border bg-black/30 px-2 py-1 text-terminal-text"
              value={riskDraft.confidence_threshold}
              onChange={(e) => setRiskDraft((prev) => ({ ...prev, confidence_threshold: Number(e.target.value) }))}
            />
          </label>
          <label className="text-xs text-terminal-muted" title="Maximum position size">
            Position Size
            <input
              type="number"
              step="0.01"
              className="mt-1 w-full rounded border border-terminal-border bg-black/30 px-2 py-1 text-terminal-text"
              value={riskDraft.max_position_size}
              onChange={(e) => setRiskDraft((prev) => ({ ...prev, max_position_size: Number(e.target.value) }))}
            />
          </label>
          <label className="text-xs text-terminal-muted" title="Daily loss guard">
            Daily Loss
            <input
              type="number"
              step="1"
              className="mt-1 w-full rounded border border-terminal-border bg-black/30 px-2 py-1 text-terminal-text"
              value={riskDraft.max_daily_loss}
              onChange={(e) => setRiskDraft((prev) => ({ ...prev, max_daily_loss: Number(e.target.value) }))}
            />
          </label>
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
