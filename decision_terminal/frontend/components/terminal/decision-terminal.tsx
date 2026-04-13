"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardTitle } from "@/components/ui/card";
import { useDecisionStream } from "@/hooks";
import { AdvancedPanels } from "@/components/terminal/advanced-panels";
import { RiskDashboard } from "@/components/terminal/risk-dashboard";
import { StrategyIntelligencePanel } from "@/components/terminal/strategy-intelligence-panel";
import { SystemControlPanel } from "@/components/terminal/system-control-panel";
import { AlphaCopilotStream } from "@/components/terminal/alpha-copilot-stream";
import { MarketMonitor } from "@/components/terminal/market-monitor";
import { LiquidityDepth } from "@/components/terminal/liquidity-depth";
import { CommandPalette } from "@/components/terminal/command-palette";
import { RiskControls } from "@/lib/types";
import { 
  Cpu, 
  Filter, 
  Info, 
  Radar, 
  ShieldAlert, 
  TrendingUp, 
  Zap 
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";

function toneFromAction(action: string) {
  if (action === "EXECUTE" || action === "EXECUTED") return "buy" as const;
  if (action === "BLOCKED") return "blocked" as const;
  if (action === "HOLD") return "neutral" as const;
  return "muted" as const;
}

function fmt(value: number) {
  if (!Number.isFinite(value)) return "--";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function toRiskDraft(risk: RiskControls): Record<string, number> {
  const out: Record<string, number> = {};
  if (!risk) return out;
  for (const [key, value] of Object.entries(risk)) {
    if (typeof value === "number" && Number.isFinite(value)) {
      out[key] = value;
    }
  }
  return out;
}

export function DecisionTerminal() {
  const {
    payload,
    filter,
    setFilter,
    activeHistory,
    replayMode,
    setReplayMode,
    replayCursor,
    replayPlaying,
    setReplayPlaying,
    replayStep,
    replaySeek,
    controlError,
    clearControlError,
    setTradingEnabled,
    setKillSwitch,
    setStrategyEnabled,
    setAsset,
    updateRisk,
    setSelectedDecisionIndex,
    selectedDecision,
  } = useDecisionStream();

  const [riskDraft, setRiskDraft] = useState<Record<string, number>>(() => toRiskDraft(payload.meta.controls.risk));
  const [advancedTab, setAdvancedTab] = useState<"inspector" | "counterfactual" | "performance" | "replay">("inspector");
  const [mounted, setMounted] = useState(false);
  const [brainPulse, setBrainPulse] = useState(false);
  
  const d = payload.decision;
  const prevTsRef = useRef<string>("");

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!d.signal.timestamp || d.signal.timestamp === "--") return;
    if (prevTsRef.current && prevTsRef.current !== d.signal.timestamp) {
      setBrainPulse(true);
      const id = setTimeout(() => setBrainPulse(false), 300);
      return () => clearTimeout(id);
    }
    prevTsRef.current = d.signal.timestamp;
  }, [d.signal.timestamp]);

  const auraClass = d.signal.side === 'BUY' ? 'aura-buy' : d.signal.side === 'SELL' ? 'aura-sell' : 'aura-neutral';
  const equityCurve = payload.performance.equity_curve || [];
  const alerts = payload.alerts || [];

  return (
    <div className={`min-h-screen bg-terminal-bg text-terminal-text selection:bg-terminal-neutral/30 aura-transition ${auraClass} ${replayMode ? "replay-tint" : ""}`}>
      <div className="starfield" />
      {/* 1. Global Institutional Header */}
      <header className="sticky top-0 z-50 topbar-glass border-b border-terminal-border/10 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-terminal-neutral/40 to-terminal-accent/20 border border-terminal-neutral/30 shadow-neon">
              <TrendingUp className="h-6 w-6 text-terminal-neutral" />
            </div>
            <div>
              <h1 className="text-xl font-black uppercase tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-terminal-text via-terminal-secondary to-terminal-muted">
                Aurelius Prime
              </h1>
              <p className="text-[10px] uppercase font-bold tracking-[0.2em] text-terminal-muted">
                Institutional Quant Hub · <span className="text-terminal-buy">Operational Status: Optimal</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Badge tone={payload.meta.connected ? "buy" : "blocked"} className="rounded-full shadow-lg font-mono">
              CONNECT: {payload.meta.connection_event}
            </Badge>
            <div className="h-8 w-[1px] bg-terminal-border/20 mx-2" />
            <div className="flex items-center gap-1.5 rounded-full bg-black/40 border border-terminal-border/10 p-1">
              {(["all", "executed", "blocked"] as const).map((k) => (
                <button
                  key={k}
                  onClick={() => setFilter(k)}
                  className={`px-3 py-1 text-[10px] uppercase font-bold tracking-widest rounded-full transition-all ${
                    filter === k ? "bg-terminal-neutral/20 text-terminal-neutral border border-terminal-neutral/30" : "text-terminal-muted hover:text-terminal-secondary"
                  }`}
                >
                  {k}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      {/* 2. System Critical Notifications */}
      <AnimatePresence>
        {(alerts.length > 0 || controlError) && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="px-6 pt-4 space-y-2 overflow-hidden"
          >
            {controlError && (
              <div className="flex items-center justify-between bg-terminal-sell/10 border border-terminal-sell/40 p-3 rounded-xl text-xs text-terminal-sell shadow-neonSell">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4" />
                  <span className="font-bold">SYSTEM CRITICAL: {controlError}</span>
                </div>
                <button onClick={clearControlError} className="hover:text-white px-3 py-1 bg-terminal-sell/20 rounded-md shadow-sm transition-colors font-bold uppercase tracking-tighter">Acknowledge</button>
              </div>
            )}
            {alerts.slice(-3).map((alert, i) => (
              <div key={i} className={`flex items-center gap-2 p-3 rounded-xl border text-xs font-medium ${
                alert.level === 'error' ? 'bg-terminal-sell/10 border-terminal-sell/40 text-terminal-sell' : 'bg-terminal-blocked/10 border-terminal-blocked/40 text-terminal-blocked'
              }`}>
                <Info className="h-4 w-4" />
                <span>{alert.message}</span>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <main className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-4 2xl:grid-cols-5">
        {/* AXIS 1: Risk & Integrity (LEFT) */}
        <div className="flex flex-col gap-6 lg:col-span-1">
          <MarketMonitor symbol={d.symbol} />
          <LiquidityDepth />
          
          <RiskDashboard
            symbol={d.position.symbol}
            assetType={payload.meta.controls.asset?.asset_type}
            positionSize={d.position.size}
            price={d.position.price}
            maxPositionSize={payload.meta.controls.risk.max_position_size}
            confidenceThreshold={payload.meta.controls.risk.confidence_threshold}
            maxDrawdown={payload.performance.max_drawdown}
            alerts={payload.alerts}
            recentRiskFailures={0}
            killSwitch={payload.meta.controls.kill_switch}
            riskState={payload.risk_state}
            fmt={fmt}
          />

          <SystemControlPanel
            controls={payload.meta.controls}
            riskDraft={riskDraft}
            setRiskDraft={setRiskDraft}
            setTradingEnabled={setTradingEnabled}
            setKillSwitch={setKillSwitch}
            setStrategyEnabled={setStrategyEnabled}
            setAsset={setAsset}
            updateRisk={updateRisk}
          />
        </div>

        {/* AXIS 2: Neural Nucleus (CENTER) */}
        <div className="flex flex-col gap-6 lg:col-span-2 2xl:col-span-3">
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            {/* Live Stance Panel */}
            <motion.div
              animate={brainPulse ? { scale: 1.005, borderColor: "rgba(55, 217, 255, 0.4)" } : { scale: 1 }}
              className={`glass-panel rounded-2xl p-6 relative overflow-hidden transition-all duration-300 ${brainPulse ? "tick-pulse" : ""}`}
            >
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  <Radar className="h-4 w-4 text-terminal-neutral animate-spin-slow" />
                  <span className="text-xs font-bold uppercase tracking-widest text-terminal-secondary">Neural Stance Monitor</span>
                </div>
                <Badge tone="muted" className="border-none font-mono tracking-tighter text-[10px]">{d.signal.timestamp}</Badge>
              </div>

              <div className="flex items-end gap-12 px-2 overflow-hidden">
                <div className="min-w-0 flex-1">
                  <label className="text-[10px] uppercase font-bold text-terminal-muted tracking-widest whitespace-nowrap">Tactical Bias</label>
                  <motion.p 
                    key={d.signal.side}
                    initial={{ scale: 0.9, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className={`text-6xl font-black italic tracking-tighter glow-number truncate ${
                      d.signal.side === 'BUY' ? 'text-terminal-buy glow-number-buy' : 
                      d.signal.side === 'SELL' ? 'text-terminal-sell glow-number-sell' : 'text-terminal-neutral'
                    }`}
                  >
                    {d.signal.side}
                  </motion.p>
                </div>
                <div className="text-right min-w-max">
                  <label className="text-[10px] uppercase font-bold text-terminal-muted tracking-widest block whitespace-nowrap">Intended Action</label>
                  <motion.p 
                    key={d.decision.action}
                    initial={{ x: 10, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    className={`text-4xl font-black uppercase tracking-tighter ${
                      d.decision.action === 'EXECUTE' ? 'text-terminal-buy' : 
                      d.decision.action === 'BLOCKED' ? 'text-terminal-sell' : 'text-terminal-secondary'
                    }`}
                  >
                    {d.decision.action}
                  </motion.p>
                </div>
              </div>

              <div className="mt-8 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-terminal-secondary">Inference Confidence</span>
                  <span className="text-[11px] font-mono text-terminal-neutral">{(Number(d.signal.confidence?.final || 0) * 100).toFixed(1)}%</span>
                </div>
                <div className="h-2.5 w-full rounded-full bg-black/40 p-0.5 border border-terminal-border/10 overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, (Number(d.signal.confidence?.final || 0) * 100))}%` }}
                    className={`h-full rounded-full relative overflow-hidden ${
                      d.signal.side === 'BUY' ? 'bg-terminal-buy' : 
                      d.signal.side === 'SELL' ? 'bg-terminal-sell' : 'bg-terminal-neutral'
                    }`}
                  >
                    <div className="absolute inset-x-0 h-full w-20 bg-white/20 blur-xl animate-shimmer" />
                  </motion.div>
                </div>
                <div className="grid grid-cols-4 gap-2 pt-2">
                  {Object.entries(d.signal.confidence || {}).slice(0, 4).map(([key, val]) => (
                    <div key={key} className="p-2 rounded-lg bg-black/30 border border-terminal-border/5 text-[10px]">
                      <div className="text-terminal-muted uppercase tracking-tighter font-bold mb-1 truncate text-center">{key.replace('_', ' ')}</div>
                      <div className="text-terminal-secondary text-center font-bold">{(Number(val) * 100).toFixed(0)}%</div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>

            {/* Performance Panel */}
            <div className="glass-panel-bright rounded-2xl p-6 relative">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  <Zap className="h-4 w-4 text-terminal-neutral" />
                  <span className="text-xs font-bold uppercase tracking-widest text-terminal-secondary">Alpha Velocity</span>
                </div>
                <div className="flex gap-4 text-right">
                  <div>
                    <div className="text-[10px] text-terminal-muted uppercase font-bold tracking-tighter">Liquidity</div>
                    <div className="text-sm font-bold text-terminal-text font-mono">${fmt(payload.performance.equity_curve?.[payload.performance.equity_curve.length - 1]?.equity || 0)}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-terminal-muted uppercase font-bold tracking-tighter">Session PnL</div>
                    <div className={`text-sm font-bold font-mono ${payload.decision.account.pnl >= 0 ? 'text-terminal-buy' : 'text-terminal-sell'}`}>
                      {payload.decision.account.pnl >= 0 ? '+' : ''}${fmt(payload.decision.account.pnl)}
                    </div>
                  </div>
                </div>
              </div>

              <div className="h-[140px] w-full mt-4">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={equityCurve}>
                    <defs>
                      <linearGradient id="colorAlpha" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(190, 100%, 65%)" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="hsl(190, 100%, 65%)" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <Area type="monotone" dataKey="equity" stroke="hsl(190, 100%, 65%)" fillOpacity={1} fill="url(#colorAlpha)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div className="grid grid-cols-3 gap-3 mt-6">
                <div className="p-3 glass-panel rounded-xl text-center">
                  <div className="text-[9px] text-terminal-muted uppercase tracking-widest font-bold">WR</div>
                  <div className="text-lg font-black text-terminal-text">{(payload.performance.win_rate * 100).toFixed(1)}%</div>
                </div>
                <div className="p-3 glass-panel rounded-xl text-center">
                  <div className="text-[9px] text-terminal-muted uppercase tracking-widest font-bold">Sharpe</div>
                  <div className="text-lg font-black text-terminal-neutral">{payload.performance.sharpe_approx.toFixed(2)}</div>
                </div>
                <div className="p-3 glass-panel rounded-xl text-center">
                  <div className="text-[9px] text-terminal-muted uppercase tracking-widest font-bold">Drawdown</div>
                  <div className="text-lg font-black text-terminal-sell">-${fmt(payload.performance.max_drawdown)}</div>
                </div>
              </div>
            </div>
          </div>

          {/* Institutional History Feed */}
          <div className="glass-panel rounded-2xl overflow-hidden flex-1">
            <div className="border-b border-terminal-border/10 bg-black/20 px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-terminal-muted" />
                <span className="text-xs font-bold uppercase tracking-widest text-terminal-secondary">Neural Decision Audit</span>
              </div>
              <span className="text-[10px] text-terminal-muted uppercase font-bold tracking-widest font-mono">Archive: {activeHistory.length} Samples</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-terminal-border/10 text-terminal-muted uppercase tracking-tighter">
                    <th className="px-6 py-4 font-bold">Timestamp</th>
                    <th className="px-6 py-4 font-bold">Asset</th>
                    <th className="px-6 py-4 font-bold">Bias</th>
                    <th className="px-6 py-4 font-bold">Verdict</th>
                    <th className="px-6 py-4 font-bold">Strategy</th>
                    <th className="px-6 py-4 font-bold text-right">Confidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-terminal-border/5">
                  <AnimatePresence>
                    {activeHistory.slice(-10).reverse().map((row, idx) => (
                      <motion.tr 
                        key={`${row.ts}-${idx}`}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="group hover:bg-terminal-neutral/5 transition-colors cursor-pointer"
                        onClick={() => setSelectedDecisionIndex(payload.history.length - 1 - idx)}
                      >
                        <td className="px-6 py-4 font-mono text-terminal-muted">{row.ts.split('T')[1]?.slice(0, 8)}</td>
                        <td className="px-6 py-4 font-bold text-terminal-text">{row.symbol}</td>
                        <td className="px-6 py-4">
                          <span className={`font-black tracking-tighter ${
                            row.signal === 'BUY' ? 'text-terminal-buy' : 
                            row.signal === 'SELL' ? 'text-terminal-sell' : 'text-terminal-neutral'
                          }`}>
                            {row.signal}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <Badge tone={toneFromAction(row.action)} className="font-mono text-[9px] rounded-sm">{row.action}</Badge>
                        </td>
                        <td className="px-6 py-4 text-terminal-secondary font-medium italic">{row.strategy}</td>
                        <td className="px-6 py-4 text-right font-mono font-bold">{(Number(row.confidence) * 100).toFixed(1)}%</td>
                      </motion.tr>
                    ))}
                  </AnimatePresence>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* AXIS 3: Cognitive Narrative (RIGHT) */}
        <div className="flex flex-col gap-6 lg:col-span-1">
          <AlphaCopilotStream stream={payload.thought_stream} />
          
          <StrategyIntelligencePanel
            rows={payload.strategy_intelligence}
            history={activeHistory}
            controls={{ strategies: payload.meta.controls.strategies, kill_switch: payload.meta.controls.kill_switch }}
            mounted={mounted}
            fmt={fmt}
          />

          <Card className="p-4 border-terminal-neutral/20 shadow-neonSoft bg-terminal-panel">
            <CardTitle className="flex items-center gap-2 text-terminal-neutral text-[11px] uppercase tracking-widest font-bold">
              <Cpu className="h-4 w-4" /> Optimization Pulse
            </CardTitle>
            <CardBody>
              <div className="flex items-center justify-between mb-3 text-[10px] font-bold uppercase">
                 <span className="text-terminal-secondary">Monte Carlo Researcher</span>
                 <span className="text-terminal-buy">OPTIMAL</span>
              </div>
              <div className="p-3 bg-black/40 rounded-xl border border-terminal-border/10">
                <p className="text-[10px] text-terminal-muted leading-relaxed italic">
                  The Aurelius Researcher just concluded a 5,000-pass permutation session. 
                  Strategy bounds for <span className="text-terminal-neutral">volatility</span> have been hardened to 0.82 sigma.
                </p>
              </div>
            </CardBody>
          </Card>
        </div>
      </main>

      {/* REPLAY & ANALYSIS FOOTER */}
      <div className="px-6 pb-6">
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
          replaySeek={replaySeek}
          activeHistory={activeHistory}
        />
      </div>

      <CommandPalette 
        setAsset={setAsset} 
        setKillSwitch={setKillSwitch} 
        setTradingEnabled={setTradingEnabled} 
      />
    </div>
  );
}
