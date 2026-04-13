"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardTitle } from "@/components/ui/card";
import { Activity, BarChart3, Layers, Zap } from "lucide-react";
import { motion } from "framer-motion";

interface MarketMetrics {
  spread: number;
  obi: number; // Order Book Imbalance
  volatility: number;
  liquidity: number;
}

interface Props {
  metrics?: MarketMetrics;
  symbol: string;
}

export function MarketMonitor({ metrics, symbol }: Props) {
  // Mock data if metrics not provided
  const m = metrics || {
    spread: 0.00042,
    obi: 0.15,
    volatility: 0.012,
    liquidity: 0.85,
  };

  return (
    <Card className="p-4 border-terminal-neutral/20 bg-terminal-panel">
      <CardTitle className="flex items-center gap-2 text-terminal-neutral text-[11px] uppercase tracking-widest font-bold">
        <Activity className="h-4 w-4" />
        Market Integrity Monitor
      </CardTitle>
      <CardBody className="space-y-4 mt-4">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-terminal-muted uppercase">Context Symbol</span>
          <span className="text-xs font-mono font-bold text-terminal-text">{symbol}</span>
        </div>

        <div className="space-y-3">
          <div className="bg-black/30 rounded-lg p-3 border border-terminal-border/10">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-terminal-muted uppercase flex items-center gap-1">
                <BarChart3 className="h-3 w-3" /> Spread (rel)
              </span>
              <span className="text-xs font-mono text-terminal-buy">{(m.spread * 100).toFixed(4)}%</span>
            </div>
            <div className="h-1 w-full bg-black/40 rounded-full overflow-hidden">
               <motion.div 
                 initial={{ width: 0 }}
                 animate={{ width: `${Math.min(100, m.spread * 5000)}%` }}
                 className="h-full bg-terminal-buy/60"
               />
            </div>
          </div>

          <div className="bg-black/30 rounded-lg p-3 border border-terminal-border/10">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-terminal-muted uppercase flex items-center gap-1">
                <Layers className="h-3 w-3" /> Book Imbalance (OBI)
              </span>
              <span className={`text-xs font-mono ${Math.abs(m.obi) > 0.3 ? 'text-terminal-sell' : 'text-terminal-secondary'}`}>
                {m.obi > 0 ? '+' : ''}{(m.obi * 100).toFixed(1)}%
              </span>
            </div>
            <div className="h-1 w-full bg-black/40 rounded-full relative">
               <motion.div 
                 initial={{ width: '50%' }}
                 animate={{ width: `${50 + (m.obi * 50)}%` }}
                 className={`h-full absolute left-0 ${m.obi >= 0 ? 'bg-terminal-buy/60' : 'bg-terminal-sell/60'}`}
               />
               <div className="absolute left-1/2 top-0 h-full w-[1px] bg-white/20" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="bg-black/30 rounded-lg p-3 border border-terminal-border/10">
              <span className="text-[9px] text-terminal-muted uppercase flex items-center gap-1 mb-1">
                <Zap className="h-3 w-3" /> Volatility
              </span>
              <span className="text-sm font-mono text-terminal-text">{(m.volatility * 100).toFixed(2)}%</span>
            </div>
            <div className="bg-black/30 rounded-lg p-3 border border-terminal-border/10">
              <span className="text-[9px] text-terminal-muted uppercase flex items-center gap-1 mb-1">
                <Activity className="h-3 w-3" /> Liquidity
              </span>
              <span className="text-sm font-mono text-terminal-buy">STABLE</span>
            </div>
          </div>
        </div>

        <div className="p-2 rounded border border-terminal-neutral/20 bg-terminal-neutral/5 flex items-center gap-3">
           <div className="h-2 w-2 rounded-full bg-terminal-neutral animate-pulse" />
           <span className="text-[9px] text-terminal-secondary leading-tight">
             Neural Engine detecting <span className="text-terminal-neutral">Regime: Range</span> with 84% variance confidence.
           </span>
        </div>
      </CardBody>
    </Card>
  );
}
