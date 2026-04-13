"use client";

import { motion } from "framer-motion";

interface DepthLevel {
  price: number;
  size: number;
}

interface Props {
  bids?: DepthLevel[];
  asks?: DepthLevel[];
}

export function LiquidityDepth({ bids, asks }: Props) {
  // Mock institutional depth if not provided
  const mockupBids = bids || Array.from({ length: 12 }, (_, i) => ({ price: 100 - i * 0.1, size: Math.random() * 50 + 20 }));
  const mockupAsks = asks || Array.from({ length: 12 }, (_, i) => ({ price: 100.1 + i * 0.1, size: Math.random() * 50 + 20 }));

  const maxSize = Math.max(...mockupBids.map(b => b.size), ...mockupAsks.map(a => a.size));

  return (
    <div className="glass-panel rounded-xl p-4 overflow-hidden border-terminal-neutral/10 bg-black/40 shadow-panel">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-bold uppercase tracking-widest text-terminal-muted">Liquidity Depth (L2)</span>
        <span className="text-[10px] font-mono text-terminal-neutral">Slippage: { (Math.random() * 0.02).toFixed(3) }%</span>
      </div>

      <div className="grid grid-cols-2 gap-4 h-[140px]">
        {/* Bids Column (BUY walls) */}
        <div className="flex flex-col-reverse justify-end gap-1 overflow-hidden">
          {mockupBids.map((b, i) => (
            <div key={`bid-${i}`} className="flex items-center justify-end gap-2 group">
              <span className="text-[9px] font-mono text-terminal-muted opacity-0 group-hover:opacity-100 transition-opacity">
                {b.price.toFixed(2)}
              </span>
              <div 
                className="h-1.5 rounded-l-sm bg-gradient-to-l from-terminal-buy/40 to-transparent relative"
                style={{ width: `${(b.size / maxSize) * 100}%` }}
              >
                {i === 0 && (
                   <motion.div 
                     className="absolute right-0 top-0 h-full w-1 bg-terminal-buy shadow-[0_0_8px_rgba(52,211,153,0.8)]"
                     animate={{ opacity: [0.3, 1, 0.3] }}
                     transition={{ repeat: Infinity, duration: 1.5 }}
                   />
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Asks Column (SELL walls) */}
        <div className="flex flex-col justify-end gap-1 overflow-hidden">
          {mockupAsks.map((a, i) => (
            <div key={`ask-${i}`} className="flex items-center gap-2 group">
              <div 
                className="h-1.5 rounded-r-sm bg-gradient-to-r from-terminal-sell/40 to-transparent relative"
                style={{ width: `${(a.size / maxSize) * 100}%` }}
              >
                 {i === 0 && (
                   <motion.div 
                     className="absolute left-0 top-0 h-full w-1 bg-terminal-sell shadow-[0_0_8px_rgba(217,70,239,0.8)]"
                     animate={{ opacity: [0.3, 1, 0.3] }}
                     transition={{ repeat: Infinity, duration: 1.5 }}
                   />
                )}
              </div>
              <span className="text-[9px] font-mono text-terminal-muted opacity-0 group-hover:opacity-100 transition-opacity">
                {a.price.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-terminal-border/10 pt-2">
        <div className="flex items-center gap-3">
           <div className="flex items-center gap-1">
             <div className="h-1.5 w-1.5 rounded-full bg-terminal-buy" />
             <span className="text-[9px] text-terminal-muted uppercase">BID</span>
           </div>
           <div className="flex items-center gap-1">
             <div className="h-1.5 w-1.5 rounded-full bg-terminal-sell" />
             <span className="text-[9px] text-terminal-muted uppercase">ASK</span>
           </div>
        </div>
        <span className="text-[9px] font-bold text-terminal-muted uppercase tracking-tighter italic">Walls Detected: STABLE</span>
      </div>
    </div>
  );
}
