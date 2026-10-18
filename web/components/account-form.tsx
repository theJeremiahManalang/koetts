"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { CatalogHeader } from "./catalog-header";

export function AccountForm({ mode }: { mode: "login" | "signup" }) {
  const signup = mode === "signup";
  const [showPassword, setShowPassword] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setSubmitted(true); }
  return <div className="catalog-shell"><CatalogHeader /><main className="account-page"><Link href="/browse" className="account-back">← Back to the library</Link><div className="account-layout"><section className="account-intro"><p className="eyebrow">YOUR NEXT CHAPTER STARTS HERE</p><h1>Good stories.<br /><span>More ways to enjoy them.</span></h1><p>A space for the stories you love,<br />whether you read them or listen.</p><div className="account-decoration" aria-hidden="true">▤ <span>♫</span></div></section><section className="account-card" aria-labelledby="account-title"><p className="eyebrow">KoeTTS</p><h2 id="account-title">{signup ? "Start your next chapter" : "Welcome back"}</h2><p>{signup ? "Make room for a new world of stories." : "A good story is waiting for you."}</p><div className="account-preview">Account preview · Sign-in is not connected yet.</div><form onSubmit={submit}>
    {signup && <label className="field-label">Name<input required name="name" autoComplete="name" placeholder="Your name" maxLength={100} /></label>}
    <label className="field-label">Email address<input required name="email" type="email" autoComplete="email" placeholder="you@example.com" /></label>
    <label className="field-label" htmlFor="account-password">Password</label><div className="account-password"><input id="account-password" required name="password" type={showPassword ? "text" : "password"} minLength={8} autoComplete={signup ? "new-password" : "current-password"} placeholder="At least 8 characters" /><button type="button" aria-controls="account-password" aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>{showPassword ? "Hide" : "Show"}</button></div>
    <button type="submit" className="button primary account-submit">{signup ? "Preview sign up" : "Preview log in"} <span aria-hidden="true">→</span></button>
    {submitted && <p className="account-feedback" role="status">Your form is ready. This preview does not create an account or sign you in. <Link href="/browse">Continue browsing →</Link></p>}
    </form><p className="account-switch">{signup ? "Already have an account?" : "New to KoeTTS?"} <Link href={signup ? "/login" : "/signup"}>{signup ? "Log in" : "Sign up"}</Link></p></section></div></main></div>;
}
