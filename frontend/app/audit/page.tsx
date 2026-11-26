"use client";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, Table, Td } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";

const PAGE = 50;

export default function AuditPage() {
  const [event, setEvent] = useState("");
  const [outcome, setOutcome] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error } = useApi<AuditEvent[]>(`/audit${qs({ event, outcome, limit: String(PAGE), offset: String(offset) })}`);
  const sel = "rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm";
  return (
    <>
      <PageHeader title="Audit History" subtitle="Append-only record of scans, reviews, dry-runs, approvals, executions, verifications and settings changes" />
      <div className="mb-4 flex flex-wrap gap-2">
        <label className="flex flex-col text-xs text-slate-500">Event
          <select className={sel} value={event} onChange={(e) => { setEvent(e.target.value); setOffset(0); }}>
            <option value="">All</option>
            {["scan", "recommendation.", "action.", "account.", "settings.", "demo.", "assistant."].map((x) => <option key={x} value={x}>{x.replace(".", "")}</option>)}
          </select>
        </label>
        <label className="flex flex-col text-xs text-slate-500">Outcome
          <select className={sel} value={outcome} onChange={(e) => { setOutcome(e.target.value); setOffset(0); }}>
            <option value="">All</option>{["success", "denied", "failed", "info"].map((x) => <option key={x}>{x}</option>)}
          </select>
        </label>
      </div>
      {error && <ErrorBox msg={error} />}
      <Card actions={<div className="flex gap-2">
        <Button small variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer</Button>
        <Button small variant="secondary" disabled={(data?.length ?? 0) < PAGE} onClick={() => setOffset(offset + PAGE)}>Older</Button>
      </div>} title={`Events ${offset + 1}–${offset + (data?.length ?? 0)}`}>
        {!data ? <Loading /> : data.length === 0 ? <Empty>No events.</Empty> : (
          <Table head={["Time", "Actor", "Event", "Target", "Outcome", "Details"]}>
            {data.map((e) => (
              <tr key={e.id}>
                <Td className="whitespace-nowrap text-xs">{new Date(e.ts).toLocaleString()}</Td>
                <Td className="text-xs">{e.actor} <span className="text-slate-400">({e.role})</span></Td>
                <Td className="font-mono text-xs">{e.event}</Td>
                <Td className="text-xs">{e.target_type === "recommendation" && e.target_id !== "-"
                  ? <Link className="text-brand-700 hover:underline" href={`/recommendations/${e.target_id}`}>{e.target_id}</Link> : `${e.target_type} ${e.target_id}`}</Td>
                <Td><Badge color={e.outcome === "success" ? "green" : e.outcome === "info" ? "gray" : "red"}>{e.outcome}</Badge></Td>
                <Td className="max-w-md"><details className="text-xs"><summary className="cursor-pointer text-slate-500">view</summary>
                  <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-50 p-2">{JSON.stringify(e.details, null, 2)}</pre></details></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}
