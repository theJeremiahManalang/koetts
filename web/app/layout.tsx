import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Manga Reader · Audio Studio", description: "Review manga dialogue, direct character voices, and export your audiobook." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
