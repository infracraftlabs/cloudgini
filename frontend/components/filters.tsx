"use client";
import { useApi } from "@/lib/api";
import { Button } from "./ui";

export type FilterState = Partial<Record<"provider" | "project" | "environment" | "resource_type" | "state" | "date_from" | "date_to", string>>;

const LABELS: Record<string, string> = {
  provider: "Provider", project: "Project", environment: "Environment", resource_type: "Resource type", state: "Status",
};

export function FilterBar({ value, onChange, show = ["provider", "project", "environment", "resource_type", "state", "dates"] }: {
  value: FilterState; onChange: (v: FilterState) => void; show?: string[];
}) {
  const { data } = useApi<Record<string, string[]>>("/filters");
  const sel = "rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm";
  return (
    <div className="mb-5 flex flex-wrap items-end gap-2">
      {(["provider", "project", "environment", "resource_type", "state"] as const).filter((k) => show.includes(k)).map((k) => (
        <label key={k} className="flex flex-col text-xs text-slate-500">
          {LABELS[k]}
          <select className={sel} value={value[k] ?? ""} onChange={(e) => onChange({ ...value, [k]: e.target.value || undefined })}>
            <option value="">All</option>
            {k === "state" && <option value="open">open (not verified/rejected)</option>}
            {(data?.[k] ?? []).map((o) => <option key={o} value={o}>{o.replaceAll("_", " ")}</option>)}
          </select>
        </label>
      ))}
      {show.includes("dates") && (
        <>
          <label className="flex flex-col text-xs text-slate-500">From
            <input type="date" className={sel} value={value.date_from ?? ""} onChange={(e) => onChange({ ...value, date_from: e.target.value || undefined })} />
          </label>
          <label className="flex flex-col text-xs text-slate-500">To
            <input type="date" className={sel} value={value.date_to ?? ""} onChange={(e) => onChange({ ...value, date_to: e.target.value || undefined })} />
          </label>
        </>
      )}
      {Object.values(value).some(Boolean) && <Button variant="ghost" small onClick={() => onChange({})}>Clear filters</Button>}
    </div>
  );
}
