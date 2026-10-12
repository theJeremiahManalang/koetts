import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Manga text", description: "Extract text from a manga panel." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
