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
