import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Manga Reader", description: "Read, listen, and explore your manga one panel at a time." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
