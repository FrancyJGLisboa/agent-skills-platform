// Small presentational primitives shared by every screen. Tailwind only; no runtime deps.
import { clsx } from "clsx";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { Loader2 } from "lucide-react";

type Variant = "default" | "primary" | "ghost" | "danger";

export function Button({
  variant = "default", size = "md", loading, className, children, disabled, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-md border font-medium transition-colors whitespace-nowrap",
        "disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-accent",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-[13px]",
        variant === "default" && "border-line bg-surface text-ink hover:bg-surface-2",
        variant === "primary" && "border-accent bg-accent text-accent-ink hover:opacity-90",
        variant === "ghost" && "border-transparent bg-transparent text-ink-2 hover:bg-surface-2 hover:text-ink",
        variant === "danger" && "border-line bg-surface text-err hover:bg-err-bg",
        className,
      )}
    >
      {loading && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  );
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={clsx(
        "h-8 w-full rounded-md border border-line bg-surface px-2.5 text-[13px] text-ink placeholder:text-ink-3",
        "focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20",
        className,
      )}
    />
  );
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={clsx(
        "h-8 rounded-md border border-line bg-surface px-2 text-[13px] text-ink",
        "focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20",
        className,
      )}
    >
      {children}
    </select>
  );
}

export function Pill({ tone = "neutral", children, title }: { tone?: "neutral" | "ok" | "warn" | "err" | "accent"; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center rounded-full px-2 py-px text-[11px] font-medium leading-4",
        tone === "neutral" && "bg-surface-2 text-ink-2",
        tone === "ok" && "bg-ok-bg text-ok",
        tone === "warn" && "bg-warn-bg text-warn",
        tone === "err" && "bg-err-bg text-err",
        tone === "accent" && "bg-accent/10 text-accent",
      )}
    >
      {children}
    </span>
  );
}

export function Switch({ checked, onChange, disabled, label }: { checked: boolean; onChange: () => void; disabled?: boolean; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={(e) => { e.stopPropagation(); onChange(); }}
      className={clsx(
        "relative h-5 w-9 shrink-0 rounded-full transition-colors disabled:opacity-50",
        checked ? "bg-accent" : "bg-ink-3/40",
      )}
    >
      <span className={clsx("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform", checked ? "translate-x-4" : "translate-x-0")} />
    </button>
  );
}

export function Field({ label, hint, children }: { label: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[12px] text-ink-3">{hint}</span>}
    </label>
  );
}

export function PageHeader({ title, count, children }: { title: string; count?: number; children?: ReactNode }) {
  return (
    <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b border-line bg-bg/95 px-6 backdrop-blur">
      <h1 className="text-[15px] font-semibold">
        {title}
        {count !== undefined && <span className="ml-2 font-normal text-ink-3">{count}</span>}
      </h1>
      <div className="ml-auto flex items-center gap-2">{children}</div>
    </header>
  );
}

export function Empty({ icon, title, hint, action }: { icon: ReactNode; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-24 text-center">
      <div className="text-ink-3">{icon}</div>
      <p className="font-medium">{title}</p>
      {hint && <p className="max-w-sm text-ink-2">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function TagChips({ tags, onPick, max = 4 }: { tags: string[]; onPick?: (tag: string) => void; max?: number }) {
  const shown = tags.slice(0, max);
  const hidden = tags.length - shown.length;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {shown.map((t) => (
        <button
          key={t}
          onClick={(e) => { e.stopPropagation(); onPick?.(t); }}
          className="rounded-full bg-surface-2 px-2 py-px text-[11px] text-ink-2 hover:text-ink"
        >
          {t}
        </button>
      ))}
      {hidden > 0 && <span className="text-[11px] text-ink-3" title={tags.slice(max).join(", ")}>+{hidden}</span>}
    </span>
  );
}

/** Left-truncating path so the skill directory name at the end stays visible. */
export function PathText({ path, className }: { path: string; className?: string }) {
  return (
    <span dir="rtl" title={path} className={clsx("block overflow-hidden text-ellipsis whitespace-nowrap text-left font-mono text-[11px] text-ink-3", className)}>
      <bdi>{path}</bdi>
    </span>
  );
}
