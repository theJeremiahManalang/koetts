import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "../features/identity/auth-provider";

export const metadata: Metadata = { title: "KoeTTS · Audio Studio", description: "Review manga dialogue, direct character voices, and export your audiobook." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AuthProvider>{children}</AuthProvider></body></html>;
}
