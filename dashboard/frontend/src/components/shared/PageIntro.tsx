import type { ReactNode } from "react";

export function PageIntro({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return <div className="page-intro"><div><div className="eyebrow accent-eyebrow">{eyebrow}</div><h2>{title}</h2><p>{description}</p></div>{actions && <div className="page-actions">{actions}</div>}</div>;
}
