import type { Metadata } from "next";
import { AuthForm } from "../../features/identity/auth-form";
export const metadata: Metadata = { title: "Sign up · KoeTTS" };
export default function SignupPage() { return <AuthForm mode="signup" />; }
