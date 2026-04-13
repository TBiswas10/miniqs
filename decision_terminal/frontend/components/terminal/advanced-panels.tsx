"use client";

import { Badge } from "@/components/ui/badge";
import { DecisionPayload } from "@/lib/types";
import { Play, Square, StepBack, StepForward, Terminal, Activity, Zap, History, FileText } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { motion, AnimatePresence } from "framer-motion";

type AdvancedTab = "inspector" | "counterfactual" | "performance" | "replay" | "station_report";

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
  replaySeek: (cursor: number) => void;
  activeHistory: DecisionPayload["history"];
  healthReport?: string;
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
  replaySeek,
  activeHistory,
}: Props) {
  return (
    <section className="mb-3 rounded-2xl glass-panel p-4 shadow-panel border-terminal-border/10">
      <div className="mb-4 flex flex-wrap items-center gap-3 border-b border-terminal-border/10 pb-3">
        {([
          ["inspector", "Neural Inspector", Terminal],
          ["counterfactual", "Counterfactuals", Activity],
          ["performance", "Alpha Analytics", Zap],
          ["replay", "Decision Audit", History],
          ["station_report", "Station Report", FileText],
        ] as const).map(([id, label, Icon]) => (
          <button
            key={id}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-[10px] font-black uppercase tracking-[0.15em] transition-all ${advancedTab === id ? "bg-terminal-neutral/10 text-terminal-neutral border border-terminal-neutral/40 shadow-neonSoft" : "text-terminal-muted hover:text-terminal-secondary border border-transparent"}`}
            onClick={() => setAdvancedTab(id)}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {advancedTab === "inspector" && (
          <motion.div 
            key="inspector"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            className="grid grid-cols-1 gap-4 xl:grid-cols-3"
          >
            <div className="rounded-xl border border-terminal-border/20 bg-black/40 p-4 xl:col-span-2">
              <p className="text-[10px] uppercase font-bold tracking-widest text-terminal-muted mb-3 flex items-center gap-2">
                <Terminal className="h-3 w-3" /> Log Depth: Inference Reason
              </p>
              <div className="p-4 rounded-lg bg-black/40 border border-terminal-border/10">
                <p className="text-sm text-terminal-text font-medium leading-relaxed italic">
                  "{selectedDecision?.reason ?? payload.decision_inspector.reasoning}"
                </p>
              </div>
              <pre className="mt-4 max-h-[180px] overflow-auto whitespace-pre-wrap text-[11px] text-terminal-secondary font-mono bg-black/20 p-3 rounded-lg border border-white/5">
                {JSON.stringify(selectedDecision?.raw ?? payload.decision_inspector.full_object, null, 2)}
              </pre>
            </div>
            <div className="rounded-xl border border-terminal-border/20 bg-black/40 p-4">
              <p className="text-[10px] uppercase font-bold tracking-widest text-terminal-muted mb-3">Deterministic Risk Gates</p>
              <div className="space-y-2">
                {(selectedDecision?.risk_checks ?? payload.decision_inspector.risk_checks).map((check) => (
                  <div key={check.key} className="flex items-center justify-between rounded-lg border border-terminal-border/10 px-3 py-2 text-[11px] bg-black/20">
                    <span className="font-bold text-terminal-secondary">{check.label}</span>
                    <Badge tone={check.passed ? "buy" : "sell"} className="font-mono">{check.passed ? "VALID" : "FAILED"}</Badge>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}

        {advancedTab === "counterfactual" && (
          <motion.div 
            key="counterfactual"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            className="rounded-xl border border-terminal-border/20 bg-black/40 p-4"
          >
            <p className="text-[10px] uppercase font-bold tracking-widest text-terminal-muted mb-3 italic">Simulated Blocked Portfolio Trajectory</p>
            <div className="h-[280px] overflow-auto rounded-xl border border-terminal-border/10 bg-black/30">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-[#0a101b] z-10">
                  <tr className="border-b border-terminal-border/20 text-terminal-muted uppercase font-bold">
                    <th className="px-4 py-3">Timestamp</th>
                    <th className="px-4 py-3">Strategy</th>
                    <th className="px-4 py-3 text-center">Bias</th>
                    <th className="px-4 py-3">Entry</th>
                    <th className="px-4 py-3">Exit</th>
                    <th className="px-4 py-3 text-right">Potential PnL</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {payload.counterfactuals.map((row, idx) => (
                    <tr key={`${row.ts}-${idx}`} className="hover:bg-white/5 transition-colors">
                      <td className="px-4 py-3 text-terminal-muted">{row.ts.slice(11, 19) || row.ts}</td>
                      <td className="px-4 py-3 font-bold text-terminal-secondary">{row.strategy}</td>
                      <td className="px-4 py-3 text-center"><Badge tone={toneFromSignal(row.side)} className="rounded-sm">{row.side}</Badge></td>
                      <td className="px-4 py-3 text-terminal-text">{fmt(row.entry_price)}</td>
                      <td className="px-4 py-3 text-terminal-text">{fmt(row.simulated_exit_price)}</td>
                      <td className={`px-4 py-3 text-right font-black ${row.simulated_pnl >= 0 ? "text-terminal-buy" : "text-terminal-sell"}`}>
                        {row.simulated_pnl >= 0 ? '+' : ''}${fmt(row.simulated_pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}

        {advancedTab === "performance" && (
          <motion.div 
            key="performance"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            className="grid grid-cols-1 gap-4 xl:grid-cols-3"
          >
             <div className="xl:col-span-2 rounded-xl border border-terminal-border/20 bg-black/40 p-4">
              <p className="text-[10px] uppercase font-bold tracking-widest text-terminal-muted mb-4">Neural Performance Matrix</p>
              <div className="h-[240px]">
                {mounted ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={payload.performance.equity_curve}>
                      <defs>
                        <linearGradient id="performGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="hsl(145, 100%, 65%)" stopOpacity={0.4}/>
                          <stop offset="95%" stopColor="hsl(145, 100%, 65%)" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="idx" hide />
                      <YAxis hide domain={['dataMin - 10', 'dataMax + 10']} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#020617", border: "1px solid rgba(119, 162, 249, 0.2)", borderRadius: '12px', fontSize: '10px' }}
                        formatter={(v: number) => [`$${fmt(Number(v))}`, 'Equity']}
                      />
                      <Area type="monotone" dataKey="equity" stroke="hsl(145, 100%, 65%)" fill="url(#performGradient)" strokeWidth={3} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : <div className="h-full w-full bg-black/20 animate-pulse rounded-lg" />}
              </div>
            </div>
            <div className="space-y-3">
              <div className="rounded-xl border border-terminal-border/20 bg-black/40 p-4">
                <p className="text-[10px] uppercase font-bold tracking-widest text-terminal-muted mb-3 flex items-center justify-between">
                  Primary Alpha Shards
                  <Zap className="h-3.5 w-3.5 text-terminal-buy" />
                </p>
                <div className="space-y-3">
                   <div className="flex justify-between items-center bg-black/20 p-2 rounded-lg border border-white/5">
                      <span className="text-[10px] text-terminal-muted uppercase">Avg Capture</span>
                      <span className="text-sm font-mono font-bold text-terminal-text">${fmt(payload.performance.avg_profit)}</span>
                   </div>
                   <div className="flex justify-between items-center bg-black/20 p-2 rounded-lg border border-white/5">
                      <span className="text-[10px] text-terminal-muted uppercase">Max Drawdown</span>
                      <span className="text-sm font-mono font-bold text-terminal-sell">-${fmt(payload.performance.max_drawdown)}</span>
                   </div>
                   <div className="flex justify-between items-center bg-black/20 p-2 rounded-lg border border-white/5">
                      <span className="text-[10px] text-terminal-muted uppercase">Sharpe Approx</span>
                      <span className="text-sm font-mono font-bold text-terminal-neutral">{payload.performance.sharpe_approx.toFixed(2)}</span>
                   </div>
                </div>
              </div>
              <div className="p-3 bg-terminal-neutral/5 rounded-xl border border-terminal-neutral/20 border-dashed">
                 <p className="text-[9px] text-terminal-secondary italic leading-relaxed">
                   Performance shards indicate a high-conviction recovery phase. Volatility scaling is currently at 1.4x baseline.
                 </p>
              </div>
            </div>
          </motion.div>
        )}

        {advancedTab === "replay" && (
          <motion.div 
            key="replay"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            className="rounded-xl border border-terminal-border/20 bg-black/40 p-4"
          >
            <div className="flex flex-wrap items-center justify-between mb-4">
               <div>
                  <p className="text-[10px] uppercase font-bold tracking-widest text-terminal-muted">Non-Destructive Replay Axis</p>
                  <p className="text-[12px] text-terminal-secondary font-mono mt-1">Cursor at Sample: {replayCursor + 1} / {payload.replay.length}</p>
               </div>
               <div className="flex items-center gap-2">
                 <button
                   className={`rounded-lg border px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-all ${replayMode ? "border-terminal-neutral text-terminal-neutral bg-terminal-neutral/5 shadow-neonSoft" : "border-terminal-border text-terminal-muted"}`}
                   onClick={() => setReplayMode(!replayMode)}
                 >
                   {replayMode ? "Active" : "Engage"} Replay
                 </button>
                 <div className="flex items-center gap-1 bg-black/40 rounded-lg p-1 border border-terminal-border/20">
                    <button className="p-2 hover:text-terminal-neutral transition-colors" onClick={() => replayStep(-1)}><StepBack className="h-4 w-4" /></button>
                    <button className="p-2 hover:text-terminal-neutral transition-colors" onClick={() => setReplayPlaying(v => !v)}>
                      {replayPlaying ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                    </button>
                    <button className="p-2 hover:text-terminal-neutral transition-colors" onClick={() => replayStep(1)}><StepForward className="h-4 w-4" /></button>
                 </div>
               </div>
            </div>
            
            <div className="relative rounded-xl border border-terminal-border/10 bg-black/30 p-4">
              {/* Event Marker Track */}
              <div className="absolute inset-x-4 top-[18px] h-2 pointer-events-none">
                 {/* 
                   Dynamic markers for Executions and Blocks.
                   We map history entries back to the timeline for rapid audit-jumping.
                 */}
                 {payload.history.map((h, i) => {
                    // Logic to find roughly where in the replay this history event occurred
                    // If replay is same length as history or has direct mapping
                    const pos = (i / Math.max(1, payload.history.length)) * 100;
                    if (h.action !== 'EXECUTE' && h.action !== 'BLOCKED') return null;
                    return (
                      <div 
                        key={`mark-${i}`}
                        className={`absolute top-0 h-2 w-1 rounded-full shadow-[0_0_8px_rgba(0,0,0,0.5)] ${h.action === 'EXECUTE' ? 'bg-terminal-buy' : 'bg-terminal-sell'}`}
                        style={{ left: `${pos}%` }}
                      />
                    );
                 })}
              </div>
              <input
                type="range"
                min={0}
                max={Math.max(payload.replay.length - 1, 0)}
                value={replayCursor}
                onChange={(e) => replaySeek(Number(e.target.value))}
                className="relative z-10 h-2 w-full cursor-pointer appearance-none rounded-full bg-terminal-border/30 accent-terminal-neutral"
              />
              <div className="mt-2 flex items-center justify-between text-[9px] text-terminal-muted font-bold uppercase tracking-widest">
                <span>Start</span>
                <span>Audit Window</span>
                <span>Live Feed</span>
              </div>
            </div>
          </motion.div>
        )}

        {advancedTab === "station_report" && (
          <motion.div 
            key="station_report"
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            className="rounded-xl border border-terminal-border/20 bg-black/40 p-6 overflow-auto max-h-[400px]"
          >
            <div className="flex items-center justify-between mb-6 pb-4 border-b border-terminal-border/10">
               <div>
                  <h3 className="text-lg font-black text-terminal-text uppercase tracking-widest flex items-center gap-2">
                    <FileText className="h-5 w-5 text-terminal-neutral" />
                    Autonomous Station Intelligence
                  </h3>
                  <p className="text-[10px] text-terminal-muted uppercase tracking-[0.2em] mt-1">Status: Stable | Deployment: BTC-USD V3</p>
               </div>
               <Badge tone="buy" className="rounded-sm font-black">ACTIVE</Badge>
            </div>
            
            <div className="prose prose-invert max-w-none">
                <div className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-terminal-text/90 bg-black/20 p-6 rounded-xl border border-terminal-border/10 shadow-inner">
                    {healthReport || "Station initialization in progress. Intelligence matrix sync pending..."}
                </div>
            </div>
            
            <div className="mt-6 flex items-center gap-4 text-[9px] uppercase font-bold tracking-widest text-terminal-muted italic">
                <span>Refreshed: Every 24h</span>
                <span className="h-1 w-1 rounded-full bg-terminal-border" />
                <span>Persistence: logs.db</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
