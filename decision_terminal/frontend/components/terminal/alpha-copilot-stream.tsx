"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Brain } from "lucide-react";

interface Thought {
  ts: string;
  level: string;
  stage: string;
  message: string;
}

interface Props {
  stream: Thought[];
}

export function AlphaCopilotStream({ stream }: Props) {
  return (
    <div className="flex h-full flex-col overflow-hidden glass-panel rounded-xl">
      <div className="flex items-center gap-2 border-b border-terminal-border/20 px-4 py-3 bg-black/20">
        <Brain className="h-4 w-4 text-terminal-accent animate-pulse" />
        <span className="text-xs font-bold uppercase tracking-widest text-terminal-accent">
          AlphaCopilot Narrative
        </span>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
        <div className="space-y-4">
          <AnimatePresence initial={false}>
            {stream.slice(-6).map((thought, idx) => (
              <motion.div
                key={`${thought.ts}-${idx}`}
                initial={{ opacity: 0, x: -10, y: 10 }}
                animate={{ opacity: 1, x: 0, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className={`relative pl-4 border-l-2 ${
                  thought.level === 'error' ? 'border-terminal-sell/40' : 
                  thought.level === 'warn' ? 'border-terminal-blocked/40' : 
                  'border-terminal-accent/30'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-mono text-terminal-muted">
                    {thought.ts.split('T')[1]?.slice(0, 8) || thought.ts}
                  </span>
                  <span className={`text-[10px] uppercase font-bold px-1.5 rounded-sm ${
                    thought.stage === 'risk_event' ? 'bg-terminal-sell/10 text-terminal-sell' :
                    thought.stage === 'strategy_signal' ? 'bg-terminal-buy/10 text-terminal-buy' :
                    'bg-terminal-muted/10 text-terminal-muted'
                  }`}>
                    {thought.stage.replace('_', ' ')}
                  </span>
                </div>
                <p className="text-xs text-terminal-secondary leading-relaxed">
                  {thought.message}
                </p>
                {idx === stream.length - 1 && (
                  <motion.div 
                    className="absolute -left-[5px] top-0 h-2 w-2 rounded-full bg-terminal-accent shadow-[0_0_8px_rgba(104,80,255,0.8)]"
                    animate={{ scale: [1, 1.5, 1], opacity: [0.5, 1, 0.5] }}
                    transition={{ repeat: Infinity, duration: 2 }}
                  />
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>

      <div className="bg-terminal-accent/5 px-4 py-3 border-t border-terminal-border/10">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-terminal-buy animate-pulse" />
          <span className="text-[10px] text-terminal-muted uppercase tracking-tighter">
            System Cognition: Online
          </span>
        </div>
      </div>
    </div>
  );
}
