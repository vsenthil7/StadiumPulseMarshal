import { useEffect, useState, useCallback } from 'react';
import { api } from '../api/client';
import type {
  AgentAnalysis,
  AppConfig,
  ApprovalDecision,
  Problem,
  RemediationAction,
  TimelineEntry,
} from '../types';
import { RootCauseTree } from '../components/RootCauseTree';
import { RemediationCard } from '../components/RemediationCard';
import { Timeline } from '../components/Timeline';
import { SettingsPanel } from '../components/SettingsPanel';
import { fmtTime, phaseLabel, pct } from '../utils/format';

interface TriageProps {
  operator: string;
}

export function TriagePage({ operator }: TriageProps) {
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
  const [menuOpen, setMenuOpen] = useState(false);

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

  const refreshActions = useCallback(async () => {
    const [acts, aud] = await Promise.all([api.getRemediations(false), api.getAudit()]);
    setActions(acts);
    setAudit(aud);
  }, []);

  const selectProblem = useCallback(
    async (p: Problem) => {
      setSelected(p);
      setMenuOpen(false);
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
    ? actions.filter((a) =>
        analysis.recommended_actions.some((r) => r.id === a.id),
      )
    : [];
  const live = config?.data_source === 'live';

  return (
    <div className="triage-page">
      <div className="triage-bar">
        <button
          className="menu-btn"
          onClick={() => setMenuOpen((v) => !v)}
          aria-label="Toggle problem feed"
          data-testid="menu-btn"
        >
          ☰ Feed
        </button>
        <span className="spacer" />
        <span
          className={`mode-badge ${live ? 'live' : 'mock'}`}
          data-testid="mode-badge"
        >
          <span className="dot" />
          {config ? `${config.data_source.toUpperCase()} · ${config.agent_backend}` : '…'}
        </span>
      </div>

      <div className="layout">
        {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}
        <aside className={`col-feed ${menuOpen ? 'open' : ''}`} data-testid="feed">
          <div className="section-head">
            <h2>Live problem feed</h2>
            <span className="count-pill" data-testid="open-count">
              {problems.filter((p) => p.status === 'OPEN').length}
            </span>
          </div>
          {problems.map((p) => (
            <button
              key={p.id}
              className={`problem-card ${selected?.id === p.id ? 'active' : ''}`}
              onClick={() => void selectProblem(p)}
              data-testid="problem-card"
            >
              <div className="row">
                <span className={`sev-tag sev-${p.severity}`}>{p.severity}</span>
                {p.matchday_phase && (
                  <span className="phase-tag">{phaseLabel(p.matchday_phase)}</span>
                )}
              </div>
              <div className="title">{p.title}</div>
              <div className="meta">
                <span>{p.id}</span>
                <span>{p.status}</span>
                <span>{fmtTime(p.opened_at)}</span>
              </div>
            </button>
          ))}
        </aside>

        <main className="col-detail" data-testid="detail">
          {!selected && (
            <div className="empty">
              <div className="big">Select a problem to begin triage</div>
              Live matchday incidents appear in the feed.
            </div>
          )}

          {selected && (
            <>
              <h1 className="detail-title" data-testid="detail-title">
                {selected.title}
              </h1>
              <p className="detail-impact">{selected.impact_summary}</p>

              <div className="panel">
                <header>
                  <h3>Matchday timeline correlation</h3>
                </header>
                <div className="body">
                  <Timeline
                    entries={timeline}
                    currentPhase={selected.matchday_phase}
                  />
                </div>
              </div>

              <div className="panel">
                <header>
                  <h3>Problem context</h3>
                </header>
                <div className="body">
                  <dl className="kv">
                    <dt>Problem ID</dt>
                    <dd>{selected.id}</dd>
                    <dt>Severity</dt>
                    <dd>{selected.severity}</dd>
                    <dt>Phase</dt>
                    <dd>{phaseLabel(selected.matchday_phase)}</dd>
                    <dt>Opened</dt>
                    <dd>{fmtTime(selected.opened_at)}</dd>
                    <dt>Affected</dt>
                    <dd>
                      {selected.affected_entities.map((e) => e.name).join(', ')}
                    </dd>
                  </dl>
                </div>
              </div>

              <div className="panel">
                <header>
                  <h3>Davis AI root-cause</h3>
                </header>
                <div className="body">
                  <RootCauseTree root={selected.root_cause} />
                </div>
              </div>

              <div className="panel" data-testid="agent-panel">
                <header>
                  <h3>Agent analysis</h3>
                  {analysis && (
                    <span className="agent-by">
                      {analysis.generated_by} · confidence {pct(analysis.confidence)}
                    </span>
                  )}
                </header>
                <div className="body">
                  {loading && (
                    <div className="empty">
                      <div className="spinner" />
                      <div style={{ marginTop: 10 }}>Agent reasoning…</div>
                    </div>
                  )}
                  {!loading && analysis && (
                    <>
                      <div className="agent-summary">{analysis.summary}</div>
                      <div className="agent-reasoning">{analysis.reasoning}</div>
                    </>
                  )}
                </div>
              </div>

              {!loading && analysis && (
                <div className="panel" data-testid="remediation-panel">
                  <header>
                    <h3>Recommended remediations — human approval</h3>
                  </header>
                  <div className="body">
                    {analysisActions.map((a) => (
                      <RemediationCard
                        key={a.id}
                        action={a}
                        onApprove={handleApprove}
                        onReject={handleReject}
                        onExecute={handleExecute}
                        busy={busy}
                      />
                    ))}
                  </div>
                </div>
              )}

              <SettingsPanel
                config={config}
                autoApprove={autoApprove}
                onToggleAutoApprove={handleToggleAutoApprove}
                operator={operator}
              />

              <div className="panel" data-testid="audit-panel">
                <header>
                  <h3>Decision audit log</h3>
                  <span className="count-pill">{audit.length}</span>
                </header>
                <div className="body">
                  {audit.length === 0 && (
                    <div className="hint">No decisions recorded yet.</div>
                  )}
                  {audit.map((d, i) => (
                    <div className="audit-row" key={i}>
                      <span
                        className={`status-chip ${d.approved ? 'APPROVED' : 'REJECTED'}`}
                      >
                        {d.approved ? (d.auto ? 'AUTO' : 'APPROVED') : 'REJECTED'}
                      </span>
                      <span className="who">{d.decided_by}</span>
                      <span style={{ color: 'var(--ink-3)' }}>
                        {d.reason || '—'}
                      </span>
                      <span className="when">{fmtTime(d.decided_at)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
