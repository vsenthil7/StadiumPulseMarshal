// Triage data + actions hook. Extracted from TriagePage so the page is a view
// and the data/IO lifecycle (fetch, select, approve/reject/execute, settings)
// lives here — easier to test and reason about.
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type {
  AgentAnalysis,
  AppConfig,
  ApprovalDecision,
  Problem,
  RemediationAction,
  TimelineEntry,
} from '../types';

export function useTriage(operator: string) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [selected, setSelected] = useState<Problem | null>(null);
  const [analysis, setAnalysis] = useState<AgentAnalysis | null>(null);
  const [actions, setActions] = useState<RemediationAction[]>([]);
  const [audit, setAudit] = useState<ApprovalDecision[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [autoApprove, setAutoApprove] = useState(false);

  const refreshActions = useCallback(async () => {
    const [acts, aud] = await Promise.all([api.getRemediations(false), api.getAudit()]);
    setActions(acts);
    setAudit(aud);
  }, []);

  const selectProblem = useCallback(
    async (p: Problem) => {
      setSelected(p);
      setAnalysis(null);
      setLoading(true);
      try {
        const full = await api.getProblem(p.id);
        setSelected(full);
        const a = await api.analyze(p.id);
        setAnalysis(a);
        await refreshActions();
      } finally {
        setLoading(false);
      }
    },
    [refreshActions],
  );

  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => undefined);
    api.getTimeline().then(setTimeline).catch(() => undefined);
    api
      .getProblems(false)
      .then((p) => {
        setProblems(p);
        const firstOpen = p.find((x) => x.status === 'OPEN') ?? p[0] ?? null;
        if (firstOpen) void selectProblem(firstOpen);
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleApprove = useCallback(
    async (id: string, reason: string) => {
      setBusy(true);
      try {
        await api.approve(id, operator, reason);
        await refreshActions();
      } finally {
        setBusy(false);
      }
    },
    [operator, refreshActions],
  );

  const handleReject = useCallback(
    async (id: string, reason: string) => {
      setBusy(true);
      try {
        await api.reject(id, operator, reason);
        await refreshActions();
      } finally {
        setBusy(false);
      }
    },
    [operator, refreshActions],
  );

  const handleToggleAutoApprove = useCallback(async (v: boolean) => {
    setAutoApprove(v);
    try {
      await api.updateSettings(v);
    } catch {
      /* keep UI state even if backend rejects */
    }
  }, []);

  const handleExecute = useCallback(
    async (id: string) => {
      setBusy(true);
      try {
        await api.execute(id);
        await refreshActions();
      } finally {
        setBusy(false);
      }
    },
    [refreshActions],
  );

  const analysisActions = analysis
    ? actions.filter((a) => analysis.recommended_actions.some((r) => r.id === a.id))
    : [];

  return {
    config, problems, timeline, selected, analysis, actions, audit,
    loading, busy, autoApprove, analysisActions,
    selectProblem, handleApprove, handleReject, handleToggleAutoApprove, handleExecute,
  };
}
