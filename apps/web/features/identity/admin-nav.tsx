"use client";

export function AdminNav({ active, canNavigate }: { active: "requests" | "studio"; canNavigate?: () => Promise<boolean> }) {
  return <nav className="admin-navigation" aria-label="Admin navigation">
    {([{ href: "/browse", label: "Home", id: "reader" }, { href: "/admin/requests", label: "Requests", id: "requests" }, { href: "/", label: "Studio", id: "studio" }]).map(item =>
      <a key={item.id} href={item.href} aria-current={active === item.id ? "page" : undefined} onClick={canNavigate ? async event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        if (await canNavigate()) window.location.assign(item.href);
      } : undefined}>{item.label}</a>)}
  </nav>;
}
