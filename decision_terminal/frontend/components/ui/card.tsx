import { cn } from "@/lib/utils";
import { HTMLAttributes } from "react";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "glass-panel card-hover rounded-xl2 shadow-panel",
        className,
      )}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-[11px] font-semibold uppercase tracking-[0.12em] text-terminal-secondary", className)} {...props} />;
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-3", className)} {...props} />;
}
