import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Decision Intelligence Terminal",
  description: "Bloomberg-style terminal for live bot decision transparency",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
