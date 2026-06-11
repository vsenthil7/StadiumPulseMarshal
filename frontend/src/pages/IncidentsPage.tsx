import { useCallback, useEffect, useState } from 'react';
import { api, apiExt, apiP3 } from '../api/client';
import type { Incident, IncidentState, Postmortem, Problem } from '../types';
import { IncidentLifecycle } from '../components/IncidentLifecycle';
import { useToast } from '../store/ToastStore';
import { fmtTime } from '../utils/format';

export function IncidentsPage({ operator }: { operator: string }) {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [selected, setSelected] = useState<Incident | null>(null);
  const [busy, setBusy] = useState(false);
  const [postmortem, setPostmortem] = useState<Postmortem | null>(null);
  const { notify } = useToast();

  const refresh = useCallback(async () => {
    const res = await apiExt.listIncidents({ limit: 100 });
    setIncidents(res.incidents);
    if (selected) {
      const updated = res.incidents.find((i) => i.id === selected.id);
      if (updated) setSelected(updated);
    }
  }, [selected]);

  useEffect(() => {
    void refresh();
    api.getProblems(true).then(setProblems).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const createFrom = useCallback(
    async (problemId: string) => {
      setBusy(true);
      try {
        const inc = await apiExt.createIncident(problemId);
        await refresh();
        setSelected(inc);
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const transition = useCallback(
    async (target: IncidentState) => {
      if (!selected) return;
      setBusy(true);
      try {
        const inc = await apiExt.transition(selected.id, target, operator);
        setSelected(inc);
        await refresh();
        notify(`Incident → ${target}`, 'success');
      } finally {
        setBusy(false);
      }
    },
    [selected, operator, refresh, notify],
  );

  const loadPostmortem = useCallback(async () => {
    if (!selected) return;
    try {
      const pm = await apiP3.getPostmortem(selected.id);
      setPostmortem(pm);
    } catch {
      notify('Could not generate postmortem', 'error');
    }
  }, [selected, notify]);

  const escalate = useCallback(async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const inc = await apiExt.escalate(selected.id);
      setSelected(inc);
      await refresh();
    } finally {
      setBusy(false);
    }
  }, [selected, refresh]);

  return (
    <div className="incidents-layout" data-testid="incidents-page">
      <div className="panel">
        <header>
          <h3>Open incidents</h3>
          <span className="count-pill">{incidents.length}</span>
        </header>
        <div className="body">
          {incidents.length === 0 && (
            <div className="hint">
              No incidents yet. Create one from an open problem below.
            </div>
          )}
          {incidents.map((inc) => (
            <button
              key={inc.id}
              className={`incident-row ${selected?.id === inc.id ? 'active' : ''}`}
              onClick={() => setSelected(inc)}
              data-testid="incident-row"
            >
              <span className={`sev-tag sev-${inc.severity}`}>{inc.severity}</span>
              <span className="incident-row-title">{inc.title}</span>
              <span className={`status-chip ${inc.state}`}>{inc.state}</span>
              <span className="incident-row-when">{fmtTime(inc.created_at)}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        <header>
          <h3>Create incident from open problem</h3>
        </header>
        <div className="body">
          {problems.map((p) => (
            <div className="problem-pick" key={p.id}>
              <span>{p.title}</span>
              <button
                className="btn primary"
                disabled={busy}
                onClick={() => createFrom(p.id)}
                data-testid="create-incident-btn"
              >
                Open incident
              </button>
            </div>
          ))}
        </div>
      </div>

      {selected && (
        <div className="panel" data-testid="incident-detail-panel">
          <header>
            <h3>{selected.title}</h3>
          </header>
          <div className="body">
            <IncidentLifecycle
              incident={selected}
              onTransition={transition}
              onEscalate={escalate}
              busy={busy}
            />
            <div className="hitl-actions" style={{ marginTop: 14 }}>
              <button
                className="btn"
                onClick={loadPostmortem}
                data-testid="postmortem-btn"
              >
                Generate postmortem
              </button>
            </div>
            {postmortem && postmortem.incident_id === selected.id && (
              <div className="postmortem" data-testid="postmortem">
                <h4>Postmortem</h4>
                <p className="postmortem-summary">{postmortem.summary}</p>
                <pre className="postmortem-md">{postmortem.markdown}</pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
