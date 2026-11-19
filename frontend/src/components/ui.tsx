import React, { useEffect } from "react";
import { IconAlert, IconCheck, IconChevronDown, IconSpinner, IconX } from "./icons";

/* ------------------------------------------------------------------ tokens */

export type Tone = "neutral" | "info" | "ok" | "warn" | "danger" | "primary" | "muted";

const toneRing: Record<Tone, string> = {
  neutral: "bg-slate-100 text-ink-700 ring-slate-200",
  muted: "bg-white text-ink-400 ring-slate-200",
  info: "bg-info-50 text-info-600 ring-sky-200",
  ok: "bg-success-50 text-success-700 ring-emerald-200",
  warn: "bg-warn-50 text-warn-700 ring-amber-200",
  danger: "bg-danger-50 text-danger-700 ring-red-200",
  primary: "bg-primary-50 text-primary-700 ring-primary-200",
};

const toneDot: Record<Tone, string> = {
  neutral: "bg-slate-400",
  muted: "bg-slate-300",
  info: "bg-sky-500",
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  danger: "bg-red-500",
  primary: "bg-primary-600",
};

/* ------------------------------------------------------------------ badges */

export function Badge({
  tone = "neutral",
  children,
  title,
  className = "",
}: {
  tone?: Tone;
  children: React.ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-medium ring-1 ring-inset ${toneRing[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function Dot({ tone = "neutral", pulse = false }: { tone?: Tone; pulse?: boolean }) {
  return (
    <span
      className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${toneDot[tone]} ${
        pulse ? "animate-pulse-soft" : ""
      }`}
    />
  );
}

const STATUS_TONE: Record<string, Tone> = {
  completed: "ok",
  approved: "ok",
  available: "ok",
  ok: "ok",
  verified: "ok",
  running: "info",
  pending: "neutral",
  awaiting_approval: "primary",
  skipped: "muted",
  cancelled: "warn",
  cancelling: "warn",
  partial: "warn",
  degraded: "warn",
  unavailable: "warn",
  rate_limited: "warn",
  timeout: "warn",
  empty: "warn",
  failed: "danger",
  error: "danger",
  rejected: "danger",
  unreachable: "danger",
};

export function statusTone(status?: string | null): Tone {
  if (!status) return "neutral";
  return STATUS_TONE[status] ?? "neutral";
}

export function StatusPill({ status, label }: { status?: string | null; label?: string }) {
  const tone = statusTone(status);
  return (
    <Badge tone={tone}>
      <Dot tone={tone} pulse={status === "running" || status === "cancelling"} />
      {label ?? (status || "unknown").replace(/_/g, " ")}
    </Badge>
  );
}

/* ------------------------------------------------------------------ buttons */

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
  icon?: React.ReactNode;
};

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  children,
  className = "",
  disabled,
  ...rest
}: ButtonProps) {
  const variants = {
    primary: "btn-primary",
    secondary: "btn-secondary",
    ghost: "btn-ghost",
    danger: "btn-danger",
  } as const;
  return (
    <button
      className={`${variants[variant]} ${size === "sm" ? "btn-sm" : ""} ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <IconSpinner size={14} /> : icon}
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ surfaces */

export function Card({
  children,
  className = "",
  padded = true,
}: {
  children: React.ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return <section className={`card ${padded ? "card-pad" : ""} ${className}`}>{children}</section>;
}

export function CardHeader({
  title,
  description,
  actions,
  icon,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="flex items-center gap-1.5 text-[15px] font-semibold text-ink-900">
          {icon && <span className="text-ink-400">{icon}</span>}
          {title}
        </h3>
        {description && <p className="mt-0.5 text-[13px] text-ink-500">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "neutral",
  icon,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: Tone;
  icon?: React.ReactNode;
}) {
  return (
    <div className="card px-4 py-3">
      <div className="flex items-center justify-between">
        <span className="text-[12px] font-medium uppercase tracking-wide text-ink-400">{label}</span>
        {icon && <span className="text-ink-300">{icon}</span>}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-[22px] font-semibold leading-tight text-ink-900">{value}</span>
        {hint && (
          <span className={`text-2xs ${tone === "danger" ? "text-danger-600" : "text-ink-400"}`}>{hint}</span>
        )}
      </div>
    </div>
  );
}

export function KeyValue({ items }: { items: { label: string; value: React.ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-[minmax(90px,auto)_1fr] gap-x-4 gap-y-1.5 text-[13px]">
      {items.map((it) => (
        <React.Fragment key={it.label}>
          <dt className="text-ink-400">{it.label}</dt>
          <dd className="min-w-0 break-words text-ink-700">{it.value}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

export function Divider({ className = "" }: { className?: string }) {
  return <hr className={`my-3 border-slate-100 ${className}`} />;
}

/* ------------------------------------------------------------------ feedback */

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-[13px] text-ink-400">
      <IconSpinner size={15} />
      {label ?? "Loading…"}
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2 py-1">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-3 animate-pulse rounded bg-slate-100" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center">
      {icon && <div className="text-ink-300">{icon}</div>}
      <p className="text-sm font-medium text-ink-700">{title}</p>
      {description && <p className="max-w-md text-[13px] text-ink-500">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorNote({ children, title = "Something went wrong" }: { children: React.ReactNode; title?: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-red-200 bg-danger-50 px-3 py-2 text-[13px] text-danger-700">
      <IconAlert size={15} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        <span className="font-medium">{title}: </span>
        <span className="break-words">{children}</span>
      </div>
    </div>
  );
}

export function Note({ children, tone = "info" }: { children: React.ReactNode; tone?: Tone }) {
  const styles: Record<string, string> = {
    info: "border-slate-200 bg-slate-50 text-ink-600",
    warn: "border-amber-200 bg-warn-50 text-warn-700",
    danger: "border-red-200 bg-danger-50 text-danger-700",
    ok: "border-emerald-200 bg-success-50 text-success-700",
    neutral: "border-slate-200 bg-slate-50 text-ink-600",
  };
  return (
    <div className={`rounded-md border px-3 py-2 text-[13px] ${styles[tone] ?? styles.info}`}>{children}</div>
  );
}

/* ------------------------------------------------------------------ inputs */

export function Field({
  label,
  hint,
  error,
  required,
  children,
  counter,
}: {
  label: string;
  hint?: React.ReactNode;
  error?: string | null;
  required?: boolean;
  children: React.ReactNode;
  counter?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 flex items-baseline justify-between">
        <span className="text-[13px] font-medium text-ink-700">
          {label} {required && <span className="text-danger-600">*</span>}
        </span>
        {counter && <span className="text-2xs text-ink-400">{counter}</span>}
      </span>
      {children}
      {hint && !error && <span className="mt-1 block text-2xs leading-4 text-ink-400">{hint}</span>}
      {error && <span className="mt-1 block text-2xs text-danger-600">{error}</span>}
    </label>
  );
}

export function Select({
  children,
  className = "",
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select className={`select ${className}`} {...rest}>
        {children}
      </select>
      <IconChevronDown size={14} className="pointer-events-none absolute right-2.5 top-2.5 text-ink-400" />
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      disabled={disabled}
      className="flex w-full items-center justify-between gap-3 rounded-md px-1 py-1.5 text-left disabled:opacity-60"
    >
      <span className="min-w-0">
        <span className="block text-[13px] font-medium text-ink-700">{label}</span>
        {hint && <span className="block text-2xs text-ink-400">{hint}</span>}
      </span>
      <span
        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
          checked ? "bg-primary-600" : "bg-slate-300"
        }`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${
            checked ? "left-4.5 translate-x-0.5" : "left-0.5"
          }`}
          style={{ left: checked ? 18 : 2 }}
        />
      </span>
    </button>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { key: T; label: string; badge?: React.ReactNode }[];
  value: T;
  onChange: (k: T) => void;
}) {
  return (
    <div className="flex items-center gap-0.5 overflow-x-auto">
      {tabs.map((t) => {
        const active = t.key === value;
        return (
          <button
            key={t.key}
            onClick={() => onChange(t.key)}
            className={`relative flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors ${
              active ? "bg-slate-100 text-ink-900" : "text-ink-500 hover:bg-slate-50 hover:text-ink-700"
            }`}
          >
            {t.label}
            {t.badge}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ modal */

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = "max-w-xl",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink-900/35 p-4 pt-[8vh] animate-fade-in">
      <div className={`w-full ${width} rounded-xl border border-slate-200 bg-white shadow-pop`}>
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold text-ink-900">{title}</h2>
            {description && <p className="mt-0.5 text-[13px] text-ink-500">{description}</p>}
          </div>
          <button onClick={onClose} className="btn-ghost btn-sm -mr-1" aria-label="Close">
            <IconX />
          </button>
        </header>
        <div className="max-h-[65vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ helpers */

export function CheckLine({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-[13px]">
      <span className={`mt-0.5 ${ok ? "text-success-600" : "text-ink-300"}`}>
        {ok ? <IconCheck size={14} /> : <span className="block h-3.5 w-3.5 rounded-full border border-slate-300" />}
      </span>
      <span className={ok ? "text-ink-700" : "text-ink-400"}>{children}</span>
    </div>
  );
}

export function fmtDuration(ms?: number | null): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m}m ${s}s`;
}

export function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function relTime(iso?: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diff = Date.now() - then;
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} d ago`;
}
