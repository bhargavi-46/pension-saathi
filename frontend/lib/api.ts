/** Typed fetch wrappers for the Pension Saathi backend. */

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

/** Schemes whose "received" status means a service/benefit was ACTIVATED
 *  (e.g. the Ayushman golden card), not cash credited via DBT — these count
 *  under "Benefits activated", never under "Payments received". */
export const NON_CASH_SCHEME_IDS = new Set(["pmjay"]);

export interface Profile {
  id: string;
  name: string | null;
  state: string | null;
  district: string | null;
  age: number | null;
  children_count: number | null;
  monthly_income: number | null;
  husband_occupation: string | null;
  onboarding_step: number;
  language: string;
}

export interface Claim {
  id: number;
  widow_id: string;
  scheme_id: string;
  scheme_name: string | null;
  status:
    | "discovered"
    | "needs_documents"
    | "action_needed"
    | "filed"
    | "tracking"
    | "received"
    | "rejected";
  tracking_id: string | null;
  filed_at: string | null;
  estimated_annual_value: number;
  reasoning: string | null;
  notes: string | null;
}

export interface Scheme {
  id: string;
  name: string;
  authority: string;
  state: string;
  benefit_amount: string;
  eligibility: string[];
  documents_required: string[];
  where_to_apply: string;
  estimated_annual_value: number;
  application_complexity: string;
  source_url: string;
}

export interface AgentActionEvent {
  id: number;
  widow_id: string;
  agent_name: "discovery" | "document" | "filing" | "tracking" | "voice";
  action: string;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface ChatMessage {
  id: number;
  role: "user" | "agent";
  content: string;
  created_at: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

export const api = {
  health: () => get<{ status: string; mock_mode: boolean }>("/health"),

  onboardingMessage: (widowId: string, message: string, language?: string) =>
    post<{
      agent_reply: string;
      done: boolean;
      profile: Profile | null;
      /** True when this message answered an information-gap question —
       *  the caller should re-run discovery with the completed profile. */
      resume_discovery?: boolean;
    }>("/agent/onboarding/message", { widow_id: widowId, message, language }),

  uploadDocument: async (widowId: string, docType: string, file: File) => {
    const form = new FormData();
    form.append("widow_id", widowId);
    form.append("doc_type", docType);
    form.append("file", file);
    const res = await fetch(`${API_URL}/agent/document/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      let detail = `upload failed: ${res.status}`;
      try {
        const body = await res.json();
        if (body.detail) detail = body.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new Error(detail);
    }
    return res.json() as Promise<{
      doc_type: string;
      extracted_data: Record<string, string | null>;
    }>;
  },

  runDiscovery: (widowId: string) =>
    post<{
      schemes_found: number;
      total_annual_value: number;
      claims: Claim[];
      /** Non-null when the pipeline HALTED on an information gap — show
       *  this question to the widow and re-run discovery after she answers. */
      followup_question?: string | null;
    }>("/agent/discovery/run", { widow_id: widowId }),

  runPrepare: (widowId: string) =>
    post<{
      submitted: number;
      needs_documents: number;
      action_needed: number;
      ask_for_uploads: string[];
      pending_uploads?: { scheme: string; docs: string[] }[];
    }>("/agent/prepare/run", { widow_id: widowId }),

  getClaims: (widowId: string) =>
    get<{ claims: Claim[]; total_annual_value: number }>(
      `/widow/${widowId}/claims`
    ),

  getMessages: (widowId: string) =>
    get<{ messages: ChatMessage[] }>(`/widow/${widowId}/messages`),

  getWidow: (widowId: string) => get<Profile>(`/widow/${widowId}`),

  getSchemes: () => get<{ schemes: Scheme[] }>("/schemes"),

  streamUrl: (widowId: string) => `${API_URL}/agent/stream/${widowId}`,
};
