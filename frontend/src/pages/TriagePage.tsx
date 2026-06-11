import { RootCauseTree } from '../components/RootCauseTree';
import { RemediationCard } from '../components/RemediationCard';
import { Timeline } from '../components/Timeline';
import { SettingsPanel } from '../components/SettingsPanel';
import { ProblemFeed } from '../components/triage/ProblemFeed';
import { DecisionAuditLog } from '../components/triage/DecisionAuditLog';
import { useTriage } from '../hooks/useTriage';
import { fmtTime, phaseLabel, pct } from '../utils/format';

interface TriageProps {
  operator: string;
}

// View only — data + actions live in useTriage(); feed and audit are their own
// components. This page composes them.
export function TriagePage({ operator }: TriageProps) {
  const t = useTriage(operator);
  const { selected, analysis, loading } = t;

  return (
    <div className="triage-page">
      <div className="layout">
        <ProblemFeed
          problems={t.problems}
          selectedId={selected?.id ?? null}
          onSelect={(p) => void t.selectProblem(p)}
        />

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
                  <Timeline entries={t.timeline} currentPhase={selected.matchday_phase} />
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
                    <dd>{selected.affected_entities.map((e) => e.name).join(', ')}</dd>
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
                    {t.analysisActions.map((a) => (
                      <RemediationCard
                        key={a.id}
                        action={a}
                        onApprove={t.handleApprove}
                        onReject={t.handleReject}
                        onExecute={t.handleExecute}
                        busy={t.busy}
                      />
                    ))}
                  </div>
                </div>
              )}

              <SettingsPanel
                config={t.config}
                autoApprove={t.autoApprove}
                onToggleAutoApprove={t.handleToggleAutoApprove}
                operator={operator}
              />

              <DecisionAuditLog audit={t.audit} />
            </>
          )}
        </main>
      </div>
    </div>
  );
}
