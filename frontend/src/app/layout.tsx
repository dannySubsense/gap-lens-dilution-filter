import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Dilution Short Filter",
  description: "Proactive SEC filing scanner and dilution short alert system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
