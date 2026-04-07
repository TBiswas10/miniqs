import { cn } from "@/lib/utils";
import { HTMLAttributes } from "react";

type Tone = "buy" | "sell" | "blocked" | "neutral" | "muted";

const toneMap: Record<Tone, string> = {
  buy: "bg-terminal-buy/15 text-terminal-buy border-terminal-buy/50",
  sell: "bg-terminal-sell/15 text-terminal-sell border-terminal-sell/50",
  blocked: "bg-terminal-blocked/15 text-terminal-blocked border-terminal-blocked/50",
  neutral: "bg-terminal-neutral/15 text-terminal-neutral border-terminal-neutral/50",
  muted: "bg-transparent text-terminal-secondary border-terminal-border",
};

export function Badge({ className, tone = "muted", ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.08em]",
        toneMap[tone],
        className,
      )}
      {...props}
    />
  );
}
