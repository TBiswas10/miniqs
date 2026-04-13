"use client";

import { useEffect, useState } from "react";
import { Search, Zap, ShieldAlert, RefreshCcw, Command } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface CommandItem {
  id: string;
  label: string;
  sub: string;
  icon: any;
  action: () => void;
}

interface Props {
  setAsset: (asset: any) => void;
  setKillSwitch: (v: boolean) => void;
  setTradingEnabled: (v: boolean) => void;
}

export function CommandPalette({ setAsset, setKillSwitch, setTradingEnabled }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((open) => !open);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const commands: CommandItem[] = [
    { 
      id: "switch-btc", 
      label: "Switch to BTC/USD", 
      sub: "Active Crypto Pipeline", 
      icon: Zap, 
      action: () => {
        setAsset({ symbol: "BTC/USD", asset_type: "crypto", market_hours: null, trading_fees: 0.001 });
        setOpen(false);
      }
    },
    { 
      id: "switch-spy", 
      label: "Switch to SPY", 
      sub: "Active Equity Pipeline", 
      icon: Zap, 
      action: () => {
        setAsset({ symbol: "SPY", asset_type: "equity", market_hours: { open: "09:30", close: "16:00", timezone: "America/New_York" }, trading_fees: 0.0001 });
        setOpen(false);
      }
    },
    { 
      id: "toggle-kill", 
      label: "Emergency Kill Switch", 
      sub: "Instant portfolio halt", 
      icon: ShieldAlert, 
      action: () => {
        setKillSwitch(true);
        setOpen(false);
      }
    },
    { 
      id: "resume-trading", 
      label: "Resume Trading", 
      sub: "De-pause execution engine", 
      icon: RefreshCcw, 
      action: () => {
        setTradingEnabled(true);
        setOpen(false);
      }
    }
  ];

  const filtered = commands.filter(c => c.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-md"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            className="fixed left-1/2 top-[20%] z-[101] w-full max-w-lg -translate-x-1/2 overflow-hidden rounded-2xl border border-terminal-neutral/20 bg-[#0a101b] shadow-2xl"
          >
            <div className="flex items-center gap-3 border-b border-terminal-border/10 px-4 py-3">
              <Search className="h-5 w-5 text-terminal-muted" />
              <input 
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search commands (Asset, System, Control)..."
                className="w-full bg-transparent text-sm text-terminal-text outline-none placeholder:text-terminal-muted font-bold"
              />
              <kbd className="rounded bg-white/5 px-2 py-0.5 text-[10px] font-bold text-terminal-muted border border-white/10 uppercase">ESC</kbd>
            </div>

            <div className="max-h-[300px] overflow-y-auto p-2">
              {filtered.length === 0 && (
                <div className="px-4 py-8 text-center text-sm text-terminal-muted italic">No commands found. Try 'BTC' or 'Kill'.</div>
              )}
              {filtered.map((cmd) => (
                <button
                  key={cmd.id}
                  onClick={cmd.action}
                  className="flex w-full items-center gap-4 rounded-xl px-4 py-3 text-left transition-all hover:bg-terminal-neutral/10 group"
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-black/40 border border-white/5 text-terminal-muted group-hover:text-terminal-neutral group-hover:border-terminal-neutral/30 transition-all">
                    <cmd.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="text-sm font-bold text-terminal-text">{cmd.label}</div>
                    <div className="text-[10px] uppercase font-bold tracking-widest text-terminal-muted">{cmd.sub}</div>
                  </div>
                  <Command className="ml-auto h-4 w-4 text-terminal-muted opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>
              ))}
            </div>

            <div className="border-t border-terminal-border/10 bg-black/20 px-4 py-2 flex items-center justify-between">
               <div className="flex gap-4 text-[9px] uppercase font-bold text-terminal-muted">
                 <span><Command className="inline h-2.5 w-2.5 mr-1" />Select</span>
                 <span><Search className="inline h-2.5 w-2.5 mr-1" />Search</span>
               </div>
               <span className="text-[9px] text-terminal-neutral/60 font-mono tracking-tighter">AURELIUS PRIME COMMAND HUB</span>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
