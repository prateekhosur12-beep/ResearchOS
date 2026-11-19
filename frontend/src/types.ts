export type Tone = "neutral" | "info" | "ok" | "warn" | "danger" | "primary";

export type StageStatus = "pending" | "running" | "completed" | "failed" | "cancelled" | "skipped";

export interface Stage {
  key: string;
  name: string;
  description: string;
  status: StageStatus;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  attempts: number;
  tool_calls: number;
  llm_calls: number;
  detail: Record<string, unknown>;
  error: string | null;
}

export interface Project {
  id: string;
  name: string;
  topic: string;
  domain: string;
  status: string;
  created_at: string;
  updated_at: string;
  research_instructions: string;
  research_questions: string[];
  paper_count: number;
  run_count: number;
  draft_count: number;
  gap_count: number;
  idea_count: number;
  last_run_status: string | null;
  active_run_id: string | null;
}

export interface QueryPlanPreview {
  topic: string;
  queries: string[];
  keywords: string[];
  intent: string;
  subtopics: string[];
  generated_by: string;
  warnings: string[];
  rejected: string[];
  used_instructions: boolean;
  max_query_chars: number;
}

export interface RunSummary {
  id: string;
  topic: string;
  status: string;
  stage: string;
  created_at: string;
  finished_at: string | null;
  stats: Record<string, any>;
  error: string | null;
  active: boolean;
  stages: Stage[];
}

export interface RunDetail extends RunSummary {
  project_id: string;
  llm_available: boolean | null;
  config: Record<string, any>;
}

export interface ProjectDetail extends Project {
  settings: Record<string, any>;
  citation_summary: Record<string, any> | null;
  draft_version: number | null;
  draft_word_count: number;
  draft_status: string | null;
  runs: RunSummary[];
  query_plan: QueryPlanPreview;
}

export interface Paper {
  id: string;
  title: string;
  doi: string | null;
  arxiv_id: string | null;
  authors: { name?: string; display_name?: string }[];
  year: number | null;
  venue: string | null;
  abstract: string | null;
  url: string | null;
  pdf_url: string | null;
  cited_by: number | null;
  type: string | null;
  sources: string[];
  retrieved_at: string;
  rank_score: number;
  rank_explain: Record<string, any>;
  is_selected: boolean;
  metadata_warnings: string[];
}

export interface Gap {
  id: string;
  title: string;
  description: string;
  rationale: string;
  kind: string;
  confidence: number;
  feasibility: string | null;
  suggested_metrics: string[];
  evidence: {
    paper_id: string;
    title?: string;
    year?: number | null;
    doi?: string | null;
    url?: string | null;
    quote?: string;
  }[];
  evidence_quotes?: { paper_id: string; quote: string }[];
  generated_by: string;
}

export interface Idea {
  id: string;
  title: string;
  research_questions: string[];
  objectives: string[];
  proposed_methodology: string;
  suggested_datasets: string[];
  metrics: string[];
  challenges: string[];
  feasibility: string;
  generated_by: string;
}

export interface DraftSection {
  name: string;
  markdown: string;
  word_count: number;
  citations?: string[];
  generated_by?: string;
}

export interface Draft {
  id: string;
  version: number;
  status: string;
  title: string;
  style: string;
  generated_by: string;
  updated_at: string;
  markdown: string;
  sections: DraftSection[];
  bibliography: {
    key: string;
    paper_id: string;
    title: string;
    authors: { name?: string }[];
    year: number | null;
    doi: string | null;
    venue?: string | null;
  }[];
}

export interface CitationEntry {
  key: string;
  title: string;
  doi: string | null;
  year: number | null;
  cited_in_text: boolean;
  doi_status: string;
  issues: string[];
  url?: string | null;
}

export interface CitationReport {
  run_id?: string;
  draft_id?: string;
  draft_version?: number;
  summary: {
    references: number;
    in_text_markers: number;
    doi_verified: number;
    doi_failed: number;
    doi_unavailable: number;
    missing_bibliography_entries: string[];
    unused_bibliography_entries: string[];
    duplicates: string[];
    entries_with_issues: number;
  };
  entries: CitationEntry[];
  claim_level_evidence_check: string;
  statement: string;
  checked_at?: string;
}

export interface RadarPayload {
  journals: {
    name: string;
    venue_in_literature?: string;
    papers_in_corpus: number;
    verification: string;
    verified_title: string | null;
    publisher: string | null;
    issn: string | null;
    similarity?: number | null;
    doi_count_total?: number | null;
    source_url?: string | null;
    note?: string;
  }[];
  funding: {
    name: string;
    funder?: string;
    openalex_id?: string | null;
    ror?: string | null;
    award_ids?: string[];
    papers?: { title: string; doi?: string | null }[];
  }[];
  collaborators: {
    name: string;
    author_key?: string | null;
    papers_in_corpus: number;
    similarity: number;
    evidence_note: string;
    papers?: { title: string }[];
  }[];
  disclaimers: Record<string, string>;
}

export interface TracePayload {
  run: {
    id: string;
    status: string;
    stage: string;
    topic?: string;
    stats: Record<string, any>;
    error: string | null;
    created_at?: string;
    finished_at?: string | null;
    stages: Stage[];
  };
  steps: {
    seq: number;
    agent: string;
    step: string;
    status: string;
    duration_ms: number | null;
    detail: Record<string, any>;
    at: string;
  }[];
  tool_invocations: {
    tool: string;
    transport: string;
    status: string;
    latency_ms: number | null;
    summary: string | null;
    error: string | null;
    args: Record<string, any>;
    at: string;
  }[];
  source_attempts: {
    attempt: number;
    source: string;
    query: string;
    status: string;
    records: number;
    latency_ms: number | null;
    http_status: number | null;
    error: string | null;
    execution_mode: string;
    retrieved_at: string;
  }[];
}

export interface SystemStatus {
  app: string;
  version: string;
  uptime_s: number;
  llm: {
    provider: string;
    available: boolean;
    model: string;
    base_url: string;
    detail: string;
    models_installed: string[];
  };
  sources: { source: string; status: string; latency_ms: number | null; detail: string; checked_at: string }[];
  mcp: {
    ok: boolean | null;
    tools?: string[];
    tool_count?: number;
    server?: Record<string, string>;
    error?: string;
    note?: string;
  };
  tool_transport: string;
  database: {
    connected: boolean;
    backend: string;
    latency_ms: number | null;
    counts: Record<string, number>;
    detail: string;
  };
  embedding: { model: string; enabled: boolean; fallback: string };
  config: Record<string, any>;
  tools: string[];
}

export interface DomainPack {
  key: string;
  label: string;
  description: string;
  evaluation_metrics: string[];
  baseline_expectations: string[];
  representative_datasets: string[];
  reproducibility_checklist: string[];
  venue_hints: string[];
  formatting_standard: string;
  manuscript_rules: string[];
}
