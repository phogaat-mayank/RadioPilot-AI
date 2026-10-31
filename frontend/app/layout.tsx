import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RadioPilot AI",
  description: "Hybrid FM radio automation & broadcast ops",
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="relative min-h-screen text-slate-100 antialiased selection:bg-[#00CEC8] selection:text-[#032023]">
        {/* Fixed 3D Volumetric Studio Background */}
        <div
          className="fixed inset-0 -z-50 pointer-events-none overflow-hidden select-none"
          aria-hidden="true"
        >
          {/* Main 3D On-Air Studio Image Layer (Crisp, High-Quality, Unblurred 2K) */}
          <div
            className="absolute inset-0 bg-cover bg-no-repeat bg-center"
            style={{
              backgroundImage: "url('/on-air-bg.jpg')",
              filter: "contrast(1.08) saturate(1.15) brightness(0.72)",
            }}
          />

          {/* Volumetric Neon Ambient Glow & 3D Depth Lighting (Harmonized with 4-Color Palette: #00CEC8, #EB4203, #FF9C5F, #FCEFC3) */}
          <div
            className="absolute inset-0"
            style={{
              background: `
                radial-gradient(circle at 26% 36%, rgba(235, 66, 3, 0.28) 0%, transparent 45%),
                radial-gradient(circle at 38% 42%, rgba(255, 156, 95, 0.18) 0%, transparent 42%),
                radial-gradient(circle at 18% 12%, rgba(0, 206, 200, 0.12) 0%, transparent 35%),
                radial-gradient(circle at 86% 82%, rgba(252, 239, 195, 0.10) 0%, transparent 45%),
                radial-gradient(ellipse 90% 90% at 50% 50%, rgba(7, 9, 13, 0.10) 0%, rgba(5, 7, 10, 0.72) 100%)
              `,
            }}
          />

          {/* Vignette Shadow for Maximum Text Contrast on Floating Tiles */}
          <div className="absolute inset-0 bg-gradient-to-b from-[#06080d]/55 via-transparent to-[#06080d]/75" />
        </div>

        {/* Floating Glass Workspace */}
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
