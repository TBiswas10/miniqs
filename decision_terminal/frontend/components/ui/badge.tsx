import { cn } from "@/lib/utils";
import { HTMLAttributes } from "react";

type Tone = "buy" | "sell" | "blocked" | "neutral" | "muted";

const toneMap: Record<Tone, string> = {
  buy: "bg-terminal-buy/12 text-terminal-buy border-terminal-buy/45 shadow-[0_0_10px_rgba(57,255,154,0.2)]",
  sell: "bg-terminal-sell/12 text-terminal-sell border-terminal-sell/45 shadow-[0_0_10px_rgba(255,92,119,0.16)]",
  blocked: "bg-terminal-blocked/12 text-terminal-blocked border-terminal-blocked/45 shadow-[0_0_10px_rgba(255,191,60,0.14)]",
  neutral: "bg-terminal-neutral/12 text-terminal-neutral border-terminal-neutral/45 shadow-[0_0_10px_rgba(55,217,255,0.2)]",
  muted: "bg-black/15 text-terminal-secondary border-terminal-border",
};

export function Badge({ className, tone = "muted", ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.1em] backdrop-blur-sm",
        toneMap[tone],
        className,
      )}
      {...props}
    />
  );
}
