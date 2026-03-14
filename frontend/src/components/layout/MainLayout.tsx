/* ─────────────────────────────────────────────
 * AuraGen — MainLayout
 * Reusable responsive wrapper that applies the
 * aura-grid system and optional Neural Pulse
 * scrollbar to content areas.
 * ───────────────────────────────────────────── */

"use client";

import { clsx } from "clsx";
import "@/styles/Grid.scss";

interface MainLayoutProps {
  children: React.ReactNode;
  columns?: number;
  className?: string;
  scrollable?: boolean;
}

export function MainLayout({
  children,
  columns,
  className,
  scrollable = true,
}: MainLayoutProps) {
  return (
    <main
      className={clsx(
        "aura-grid",
        scrollable && "aura-scroll",
        className
      )}
      style={
        columns
          ? { gridTemplateColumns: `repeat(${columns}, 1fr)` }
          : undefined
      }
    >
      {children}
    </main>
  );
}
