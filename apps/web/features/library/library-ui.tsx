import Link from "next/link";
import { AccountNav } from "../identity/account-nav";

export function LibraryHeader() {
  return <header className="library-header">
    <Link href="/browse" className="brand" aria-label="KoeTTS manga library">
      <span className="library-mark" aria-hidden="true"><i /><i /><i /></span>
      <span><span className="eyebrow">MANGA, WITH A VOICE</span><span className="brand-title">KoeTTS<span className="brand-dot">.</span></span></span>
    </Link><AccountNav />
  </header>;
}
export function MangaCover({ id, title }: { id: string; title: string }) {
  return <div className={`library-cover cover-${id}`} aria-hidden="true">
    <span className="cover-edition">KOETTS / STORY COLLECTION</span>
    <div className="cover-art"><i /><i /><i /><i /></div>
    <span className="cover-title">{title}</span><span className="cover-caption">A WORLD BETWEEN THE PANELS</span>
  </div>;
}
