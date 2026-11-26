export type Evidence = { label: string; value: unknown; source: string };
export type Check = { name: string; status: "pass" | "fail" | "unknown"; detail: string };

export type Recommendation = {
  id: string; account_id: string; resource_id: number | null; kind: "cost" | "cleanup" | "security"; rule: string;
  title: string; summary: string; severity: string; state: string;
  current_config: Record<string, unknown>; recommended_config: Record<string, unknown>;
  evidence: Evidence[]; checks: Check[]; observation_days: number | null;
  monthly_savings: number | null; savings_basis: "estimated" | "verified" | "none"; savings_method: string | null;
  confidence: string; risk: string; impact: string; procedure: string[];
  action_type: string | null; action_params: Record<string, unknown>; manual_review_reason: string | null;
  verification: Record<string, unknown> | null; data_source: "real" | "simulated";
  detected_at: string; updated_at: string;
  resource_name: string | null; resource_type: string | null; project: string | null; environment: string | null; provider: string | null;
};

export type Action = {
  id: string; recommendation_id: string; action_type: string; params: Record<string, unknown>; state: string;
  plan: { steps: string[]; before: Record<string, unknown>; after: Record<string, unknown>; preconditions: string[];
          reversible: boolean; destructive: boolean; rollback: string; resource_external_id: string };
  reversible: boolean; destructive: boolean; rollback: string; requested_by: string; approved_by: string | null;
  executed_by: string | null; result: Record<string, unknown> | null; verification: Record<string, unknown> | null;
  error: string | null; data_source: string; created_at: string; updated_at: string;
};

export type Account = {
  id: string; provider: string; name: string; scope_id: string; data_source: string; remediation_enabled: boolean;
  status: string; status_detail: string | null; last_scan_at: string | null;
};

export type AuditEvent = {
  id: number; ts: string; actor: string; role: string; event: string; target_type: string; target_id: string;
  outcome: string; details: Record<string, unknown>;
};

export type Me = { name: string; role: string; permissions: string[] };
