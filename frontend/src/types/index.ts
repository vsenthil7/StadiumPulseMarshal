export type Severity = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type ProblemStatus = 'OPEN' | 'RESOLVED' | 'CLOSED';
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export type RemediationStatus =
  | 'PROPOSED'
  | 'AWAITING_APPROVAL'
  | 'APPROVED'
  | 'REJECTED'
  | 'EXECUTED'
  | 'FAILED'
  | 'AUTO_APPROVED';

export interface Entity {
  id: string;
  name: string;
  type: string;
  tags: string[];
  health: number;
}

export interface RootCauseNode {
  entity_id: string;
  entity_name: string;
  entity_type: string;
  is_root_cause: boolean;
  confidence: number;
  contribution: string;
  children: RootCauseNode[];
}

export interface ProblemEvent {
  id: string;
  title: string;
  entity_id: string;
  timestamp: string;
  description: string;
}

export interface Problem {
  id: string;
  title: string;
  severity: Severity;
  status: ProblemStatus;
  opened_at: string;
  resolved_at: string | null;
  affected_entities: Entity[];
  root_cause: RootCauseNode | null;
  events: ProblemEvent[];
  matchday_phase: string | null;
  impact_summary: string;
}

export interface RemediationAction {
  id: string;
  problem_id: string;
  title: string;
  description: string;
  runbook: string[];
  risk: RiskLevel;
  status: RemediationStatus;
  estimated_mttr_minutes: number;
  requires_approval: boolean;
  created_at: string;
}

export interface AgentAnalysis {
  problem_id: string;
  summary: string;
  root_cause: RootCauseNode | null;
  correlated_phase: string | null;
  confidence: number;
  recommended_actions: RemediationAction[];
  reasoning: string;
  generated_by: string;
}

export interface AppConfig {
  app_name: string;
  app_version: string;
  data_source: string;
  dynatrace_live: boolean;
  gemini_live: boolean;
  agent_backend: string;
  auto_approve_low_risk: boolean;
}

export interface ApprovalDecision {
  remediation_id: string;
  approved: boolean;
  decided_by: string;
  reason: string;
  decided_at: string;
  auto: boolean;
}

export interface TimelineEntry {
  phase: string;
  label: string;
  starts_at: string;
  expected_load_multiplier: number;
}

// --- Phase 2 types ---
export type IncidentState =
  | 'DETECTED'
  | 'ACKNOWLEDGED'
  | 'INVESTIGATING'
  | 'MITIGATING'
  | 'RESOLVED'
  | 'POSTMORTEM'
  | 'CLOSED';

export type EscalationTier = 'TIER1' | 'TIER2' | 'TIER3';
export type BurnState = 'HEALTHY' | 'SLOW_BURN' | 'FAST_BURN' | 'EXHAUSTED';

export interface IncidentEvent {
  type: string;
  at: string;
  actor: string;
  detail: string;
  data: Record<string, unknown>;
}

export interface Incident {
  id: string;
  problem_id: string;
  title: string;
  severity: Severity;
  state: IncidentState;
  tier: EscalationTier;
  assignee: string | null;
  venue_id: string | null;
  match_id: string | null;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  timeline: IncidentEvent[];
  remediation_ids: string[];
  impact_summary: string;
}

export interface Page {
  total: number;
  offset: number;
  limit: number;
}

export interface ErrorBudget {
  slo_id: string;
  slo_name: string;
  target: number;
  achieved: number;
  consumed_fraction: number;
  remaining_fraction: number;
  burn_rate: number;
  state: BurnState;
  computed_at: string;
}

export interface AnalyticsSummary {
  total_incidents: number;
  open_incidents: number;
  resolved_incidents: number;
  mttr_minutes: number | null;
  mtta_minutes: number | null;
  by_severity: Record<string, number>;
  by_state: Record<string, number>;
  by_venue: Record<string, number>;
  slo_breaching: number;
  slo_total: number;
}

export interface NotificationItem {
  id: string;
  incident_id: string;
  channel: string;
  recipient: string;
  subject: string;
  body: string;
  status: string;
  created_at: string;
  sent_at: string | null;
}

export interface ScenarioInfo {
  key: string;
  name: string;
  description: string;
  venue: string;
  match: string;
  severity: Severity;
}

// --- Phase 3 types ---
export interface WebhookSubscription {
  id: string;
  url: string;
  event_types: string[];
  active: boolean;
  description: string;
  created_at: string;
  last_status: number | null;
  last_delivery_at: string | null;
  failure_count: number;
}

export interface SLOTrend {
  slo_id: string;
  slo_name: string;
  samples: number;
  latest_state: BurnState;
  latest_burn_rate: number;
  min_burn_rate: number;
  max_burn_rate: number;
  avg_burn_rate: number;
  direction: 'improving' | 'worsening' | 'stable';
  series: { burn_rate: number; state: string; at: string }[];
}

export interface Postmortem {
  incident_id: string;
  title: string;
  severity: Severity;
  final_state: string;
  summary: string;
  tta_minutes: number | null;
  ttr_minutes: number | null;
  escalation_tier: string;
  remediation_ids: string[];
  timeline: { at: string; actor: string; event: string; detail: string }[];
  markdown: string;
}

export interface ReadyState {
  status: string;
  checks: Record<string, string>;
}
