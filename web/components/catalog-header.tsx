import Link from "next/link";

export function CatalogHeader() {
  return <header className="catalog-header">
    <Link href="/browse" className="brand"><span className="brand-icon" aria-hidden="true">▤</span><span><span className="eyebrow">READ. LISTEN. IMAGINE.</span><span className="brand-title">KoeTTS<span className="brand-dot">.</span></span></span></Link>
    <nav aria-label="Main navigation"><Link href="/browse">Browse</Link><Link href="/request">Request audio</Link></nav>
    <div className="catalog-account"><Link href="/login" className="catalog-login">Log in</Link><Link href="/signup" className="button primary">Sign up <span aria-hidden="true">↗</span></Link></div>
  </header>;
}
