/* ─────────────────────────────────────────────
 * AuraGen — Root Layout
 * Dark theme with Inter font and global styles.
 * ───────────────────────────────────────────── */

import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "AuraGen — AI Image & Video Generation",
  description:
    "Premium AI-powered image and video generation platform with a liquid glass interface.",
  icons: {
    icon: "/favicon.ico",
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0a0f",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${inter.variable}`}>
      <body className="font-sans antialiased">
          {/* Skip to main content — accessibility */}
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-aura-accent focus:text-white focus:text-sm focus:font-medium focus:outline-none"
          >
            Skip to main content
          </a>
          {children}
      </body>
    </html>
  );
}
