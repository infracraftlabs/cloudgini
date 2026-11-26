"use client";
import clsx from "clsx";
import { ReactNode } from "react";
import { money } from "@/lib/api";

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("rounded-xl border border-slate-200 bg-white shadow-sm", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const tone: Record<string, string> = {
  gray: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-brand-50 text-brand-700 ring-brand-100",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  purple: "bg-violet-50 text-violet-700 ring-violet-200",
  orange: "bg-orange-50 text-orange-700 ring-orange-200",
};

export function Badge({ children, color = "gray", title }: { children: ReactNode; color?: keyof typeof tone; title?: string }) {
  return (
    <span title={title} className={clsx("inline-flex items-center whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset", tone[color])}>
      {children}
    </span>
  );
}

const severityColor: Record<string, keyof typeof tone> = { critical: "red", high: "orange", medium: "amber", low: "blue", info: "gray" };
export const SeverityBadge = ({ s }: { s: string }) => <Badge color={severityColor[s] ?? "gray"}>{s}</Badge>;

const stateColor: Record<string, keyof typeof tone> = {
  detected: "blue", reviewed: "purple", approved: "amber", executed: "amber", verified: "green",
  rejected: "gray", failed: "red", requires_manual_review: "orange",
  planned: "blue", cancelled: "gray",
};
export const StateBadge = ({ s }: { s: string }) => <Badge color={stateColor[s] ?? "gray"}>{s.replaceAll("_", " ")}</Badge>;

export function DataSourceBadge({ s }: { s: string }) {
  return s === "real"
    ? <Badge color="green" title="Read from a real cloud account">REAL</Badge>
    : <Badge color="purple" title="Synthetic data from the simulated provider">SIMULATED</Badge>;
}

export function Savings({ value, basis, method }: { value: number | null; basis: string; method?: string | null }) {
  if (value == null) return <span className="text-slate-400" title={method ?? undefined}>no figure</span>;
  return (
    <span className="inline-flex items-center gap-1.5" title={method ?? undefined}>
      <span className="font-medium tabular-nums">{money(value)}/mo</span>
      <Badge color={basis === "verified" ? "green" : "amber"}>{basis}</Badge>
    </span>
  );
}

export function Button({ children, onClick, variant = "primary", disabled, title, type = "button", small }: {
  children: ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "danger" | "ghost";
  disabled?: boolean; title?: string; type?: "button" | "submit"; small?: boolean;
}) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} title={title}
      className={clsx("inline-flex items-center gap-1.5 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        small ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
        variant === "primary" && "bg-brand-600 text-white hover:bg-brand-700",
        variant === "secondary" && "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-700",
        variant === "ghost" && "text-slate-600 hover:bg-slate-100")}>
      {children}
    </button>
  );
}

export function Kpi({ label, value, hint, color }: { label: string; value: ReactNode; hint?: ReactNode; color?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={clsx("mt-1 text-2xl font-semibold tabular-nums", color)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export const ErrorBox = ({ msg }: { msg: string }) => (
  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{msg}</div>
);
export const Notice = ({ children, color = "amber" }: { children: ReactNode; color?: "amber" | "blue" | "green" }) => (
  <div className={clsx("rounded-lg border px-3 py-2 text-sm",
    color === "amber" && "border-amber-200 bg-amber-50 text-amber-900",
    color === "blue" && "border-brand-100 bg-brand-50 text-brand-700",
    color === "green" && "border-emerald-200 bg-emerald-50 text-emerald-800")}>{children}</div>
);
export const Loading = () => <div className="py-10 text-center text-sm text-slate-400">Loading…</div>;
export const Empty = ({ children }: { children: ReactNode }) => <div className="py-8 text-center text-sm text-slate-500">{children}</div>;

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">{actions}</div>
    </div>
  );
}

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
          <tr>{head.map((h, i) => <th key={i} className="whitespace-nowrap px-3 py-2 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
    </div>
  );
}
export const Td = ({ children, className }: { children?: ReactNode; className?: string }) =>
  <td className={clsx("px-3 py-2 align-top", className)}>{children}</td>;

export function KV({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data ?? {});
  if (!entries.length) return <span className="text-slate-400">—</span>;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-slate-500">{k}</dt>
          <dd className="break-all font-mono text-slate-800">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}
