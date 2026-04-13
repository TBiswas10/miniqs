"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardTitle } from "@/components/ui/card";
import { AssetControls, RiskControls } from "@/lib/types";
import { Gauge, RefreshCcw, ShieldAlert } from "lucide-react";

type Controls = {
  trading_enabled: boolean;
  kill_switch: boolean;
  asset?: AssetControls;
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
  setAsset: (asset: AssetControls) => Promise<unknown>;
  updateRisk: (risk: Partial<RiskControls>) => Promise<unknown>;
};

const CORE_RISK_FIELDS = ["confidence_threshold", "max_position_size", "max_loss_per_session"] as const;

const RISK_LABELS: Record<string, string> = {
  confidence_threshold: "Confidence",
  max_position_size: "Max Exposure",
  max_loss_per_session: "Session Loss",
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
  setAsset,
  updateRisk,
}: Props) {
  const advancedRiskFields = Object.keys(riskDraft)
    .filter((key) => !CORE_RISK_FIELDS.includes(key as (typeof CORE_RISK_FIELDS)[number]))
    .sort();

  const renderRiskInput = (field: string) => (
    <div key={field} className="group flex flex-col">
      <label className="text-[10px] text-terminal-muted uppercase font-bold tracking-tighter mb-1 select-none">
        {RISK_LABELS[field] ?? field.replace(/_/g, " ")}
      </label>
      <input
        type="number"
        step={riskStep(field)}
        className="w-full rounded-md border border-terminal-border bg-black/40 px-3 py-1.5 text-xs text-terminal-text focus:border-terminal-neutral/50 focus:outline-none transition-all font-mono"
        value={Number.isFinite(riskDraft[field]) ? riskDraft[field] : 0}
        onChange={(e) => setRiskDraft((prev) => ({ ...prev, [field]: Number(e.target.value) }))}
      />
    </div>
  );

  const activeAsset = controls.asset ?? {
    symbol: "BTC/USD",
    asset_type: "crypto",
    market_hours: null,
    trading_fees: 0.001,
  };

  const switchAsset = async (symbol: string) => {
    const isCrypto = symbol.includes("/");
    await setAsset(
      isCrypto
        ? { symbol: "BTC/USD", asset_type: "crypto", market_hours: null, trading_fees: 0.001 }
        : { symbol: "SPY", asset_type: "equity", market_hours: { open: "09:30", close: "16:00", timezone: "America/New_York" }, trading_fees: 0.0001 },
    );
  };

  return (
    <Card className="p-4 border-terminal-neutral/10 bg-terminal-panel shadow-panel">
      <CardTitle className="flex items-center gap-2 text-terminal-muted text-[11px] uppercase tracking-widest font-bold">
        <Gauge className="h-4 w-4" /> Guardrail Management
      </CardTitle>
      <CardBody className="space-y-4 mt-4">
        <div className="rounded-xl border border-terminal-border/20 bg-black/30 p-4">
          <div className="mb-3 flex items-center justify-between text-[11px] uppercase tracking-[0.08em] font-bold text-terminal-muted">
            <span>Runtime Asset</span>
            <Badge tone="muted">{activeAsset.asset_type}</Badge>
          </div>
          <div className="flex items-center gap-2">
            {([
              { symbol: "BTC/USD", label: "BTC/USD" },
              { symbol: "SPY", label: "SPY" },
            ] as const).map((asset) => (
              <button
                key={asset.symbol}
                className={`rounded-lg border px-4 py-2 text-xs font-bold transition-all ${activeAsset.symbol === asset.symbol ? "border-terminal-neutral text-terminal-neutral bg-terminal-neutral/5" : "border-terminal-border text-terminal-muted hover:border-terminal-neutral/40 hover:text-terminal-secondary"}`}
                onClick={() => void switchAsset(asset.symbol)}
              >
                {asset.label}
              </button>
            ))}
            <button
              className="ml-auto inline-flex items-center gap-1 rounded-lg border border-terminal-border px-3 py-2 text-xs font-bold text-terminal-muted hover:bg-black/20"
              onClick={() => void setAsset(activeAsset)}
            >
              <RefreshCcw className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            className={`rounded-lg border px-4 py-2.5 text-xs font-bold uppercase tracking-widest transition-all ${controls.trading_enabled ? "border-terminal-buy text-terminal-buy bg-terminal-buy/5 shadow-neonBuy" : "border-terminal-border text-terminal-muted"}`}
            onClick={() => void setTradingEnabled(!controls.trading_enabled)}
          >
            {controls.trading_enabled ? "Running" : "Resume"}
          </button>
          <button
            className={`rounded-lg border px-4 py-2.5 text-xs font-bold uppercase tracking-widest transition-all ${controls.kill_switch ? "border-terminal-sell bg-terminal-sell/20 text-terminal-sell shadow-neonSell" : "border-terminal-border text-terminal-muted"}`}
            onClick={() => void setKillSwitch(!controls.kill_switch)}
          >
             Kill Switch
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {Object.entries(controls.strategies).map(([strategy, enabled]) => (
            <button
              key={strategy}
              className={`rounded-lg border px-3 py-2 text-[10px] uppercase font-bold tracking-tighter transition-all ${enabled ? "border-terminal-buy/40 text-terminal-secondary bg-black/20" : "border-terminal-border text-terminal-muted opacity-50"}`}
              onClick={() => void setStrategyEnabled(strategy, !enabled)}
            >
              {strategy.replace("_", " ")}
            </button>
          ))}
        </div>

        <div className="space-y-4 pt-2">
          <div className="grid grid-cols-3 gap-3">
            {CORE_RISK_FIELDS.map((field) => renderRiskInput(field))}
          </div>

          <div className="rounded-xl border border-terminal-border/20 bg-black/20 p-4">
            <p className="mb-3 text-[10px] uppercase tracking-[0.08em] font-bold text-terminal-muted">Extended Guardrails</p>
            <div className="grid grid-cols-2 gap-3">
              {advancedRiskFields.slice(0, 4).map((field) => renderRiskInput(field))}
            </div>
          </div>

          <button
            className="w-full flex items-center justify-center gap-2 rounded-xl border border-terminal-neutral/30 bg-terminal-neutral/10 py-3 text-xs font-black uppercase tracking-[0.2em] text-terminal-neutral hover:bg-terminal-neutral/20 transition-all shadow-neonSoft"
            onClick={() => void updateRisk(riskDraft)}
          >
            Apply Hardened Parameters
          </button>
        </div>
      </CardBody>
    </Card>
  );
}
