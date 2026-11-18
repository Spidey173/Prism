import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Prism", description: "Automated document proofing" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
