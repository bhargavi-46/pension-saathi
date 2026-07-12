import type { Metadata } from "next";
import { Geist, Playfair_Display } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const playfair = Playfair_Display({
  variable: "--font-playfair",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Pension Saathi — Every rupee she is owed",
  description:
    "An agentic AI companion that discovers, files and tracks every government pension entitlement for Indian widows. Built for ScriptedByHer 2.0.",
  openGraph: {
    title: "Pension Saathi",
    description:
      "The agent that finds every rupee a widow is owed — discovery, filing and tracking of government schemes, in her own language.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${playfair.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
