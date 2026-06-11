import { useEffect, useState } from 'react';
import { apiExt } from '../api/client';
import { useToast } from '../store/ToastStore';
import { useAuth } from '../lib/auth';
import { roleMeets } from '../lib/rbac';
import type {
  Runbook, RunbookExecution, PostmortemDoc, SloDef, BurnPolicy,
  FleetVenue, CostSummary,
} from '../types';

type SubTab = 'runbooks' | 'postmortems' | 'slo' | 'fleet' | 'cost';

const SUBTABS: { id: SubTab; label: string }[] = [
  { id: 'runbooks', label: 'Runbooks' },
  { id: 'postmortems', label: 'Postmortems' },
  { id: 'slo', label: 'SLO Catalog' },
  { id: 'fleet', label: 'Fleet' },
  { id: 'cost', label: 'Cost' },
];

export function EnterprisePage() {
  const [sub, setSub] = useState<SubTab>('runbooks');
  return (
    <div className="panel" data-testid="enterprise-page">
      <header>
        <h3>Enterprise</h3>
        <div className="seg-control" role="tablist" aria-label="Enterprise sections">
          {SUBTABS.map((t) => (
            <button
              key={t.id}
              className={`seg ${sub === t.id ? 'is-active' : ''}`}
              onClick={() => setSub(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>
      <div className="body">
        {sub === 'runbooks' && <Runbooks />}
        {sub === 'postmortems' && <Postmortems />}
        {sub === 'slo' && <SloCatalog />}
        {sub === 'fleet' && <Fleet />}
        {sub === 'cost' && <Cost />}
      </div>
    </div>
  );
}

function Runbooks() {
  const { session } = useAuth();
  const canRun = session ? roleMeets(session.user.role, 'responder') : false;
  const [rbs, setRbs] = useState<Runbook[]>([]);
  const [execs, setExecs] = useState<RunbookExecution[]>([]);
  const { notify } = useToast();

  const load = () => {
    apiExt.listRunbooks().then(setRbs).catch(() => setRbs([]));
    apiExt.listRunbookExecutions().then(setExecs).catch(() => setExecs([]));
  };
  useEffect(load, []);

  const run = async (id: string) => {
    try {
      await apiExt.executeRunbook(id);
      notify('Runbook executed', 'success');
      load();
    } catch {
      notify('Execution failed', 'error');
    }
  };

  return (
    <div>
      <table className="data-table">
        <thead>
          <tr><th>Name</th><th>Category</th><th>Steps</th><th>Tags</th><th /></tr>
        </thead>
        <tbody>
          {rbs.map((r) => (
            <tr key={r.id}>
              <td>{r.name}</td>
              <td>{r.category}</td>
              <td>{r.steps.length}</td>
              <td className="muted">{r.tags.join(', ')}</td>
              <td>
                {canRun && (
                  <button className="seg" onClick={() => run(r.id)}>Execute</button>
                )}
              </td>
            </tr>
          ))}
          {rbs.length === 0 && <tr><td colSpan={5} className="muted">No runbooks</td></tr>}
        </tbody>
      </table>
      {execs.length > 0 && (
        <>
          <h4 style={{ marginTop: 16 }}>Recent executions</h4>
          <table className="data-table">
            <thead><tr><th>ID</th><th>Runbook</th><th>Status</th><th>Actor</th></tr></thead>
            <tbody>
              {execs.slice(0, 8).map((e) => (
                <tr key={e.id}>
                  <td className="mono">{e.id}</td>
                  <td className="mono">{e.runbook_id}</td>
                  <td><span className="status-badge status-ok">{e.status}</span></td>
                  <td>{e.actor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function Postmortems() {
  const { session } = useAuth();
  const canWrite = session ? roleMeets(session.user.role, 'operator') : false;
  const [pms, setPms] = useState<PostmortemDoc[]>([]);
  const [title, setTitle] = useState('');
  const { notify } = useToast();

  const load = () => apiExt.listPostmortems().then(setPms).catch(() => setPms([]));
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!title.trim()) return;
    try {
      await apiExt.createPostmortem({ title: title.trim() });
      setTitle('');
      notify('Postmortem created', 'success');
      load();
    } catch {
      notify('Create failed', 'error');
    }
  };

  return (
    <div>
      {canWrite && (
        <div className="seg-control" style={{ marginBottom: 12 }}>
          <input className="text-input" placeholder="New postmortem title"
            value={title} onChange={(e) => setTitle(e.target.value)} style={{ minWidth: 240 }} />
          <button className="seg" disabled={!title.trim()} onClick={create}>Create</button>
        </div>
      )}
      <table className="data-table">
        <thead><tr><th>Title</th><th>Status</th><th>Severity</th><th>Actions</th></tr></thead>
        <tbody>
          {pms.map((p) => (
            <tr key={p.id}>
              <td>{p.title}</td>
              <td><span className="status-badge">{p.status}</span></td>
              <td>{p.severity || '—'}</td>
              <td>{p.action_items.length}</td>
            </tr>
          ))}
          {pms.length === 0 && <tr><td colSpan={4} className="muted">No postmortems</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function SloCatalog() {
  const [slos, setSlos] = useState<SloDef[]>([]);
  const [policy, setPolicy] = useState<BurnPolicy | null>(null);

  useEffect(() => { apiExt.listSloCatalog().then(setSlos).catch(() => setSlos([])); }, []);

  const showPolicy = (id: string) =>
    apiExt.getBurnPolicy(id).then(setPolicy).catch(() => setPolicy(null));

  return (
    <div>
      <table className="data-table">
        <thead><tr><th>SLO</th><th>Service</th><th>Target</th><th>Window</th><th /></tr></thead>
        <tbody>
          {slos.map((s) => (
            <tr key={s.id}>
              <td>{s.name}</td>
              <td className="mono">{s.service_id}</td>
              <td>{(s.target * 100).toFixed(2)}%</td>
              <td>{s.window_hours}h</td>
              <td><button className="seg" onClick={() => showPolicy(s.id)}>Burn policy</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {policy && (
        <>
          <h4 style={{ marginTop: 16 }}>Burn policy — {policy.slo_name}</h4>
          <table className="data-table">
            <thead><tr><th>Tier</th><th>Long/Short</th><th>Factor</th><th>Severity</th><th>Trigger error rate</th></tr></thead>
            <tbody>
              {policy.burn_tiers.map((t) => (
                <tr key={t.name}>
                  <td>{t.name}</td>
                  <td className="mono">{t.long_hours}h / {(t.short_hours * 60).toFixed(0)}m</td>
                  <td>{t.factor}×</td>
                  <td><span className={`status-badge ${t.severity === 'PAGE' ? 'status-fail' : ''}`}>{t.severity}</span></td>
                  <td className="mono">{(t.trigger_error_rate * 100).toFixed(3)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function Fleet() {
  const [venues, setVenues] = useState<FleetVenue[]>([]);
  useEffect(() => { apiExt.getFleet().then((r) => setVenues(r.venues)).catch(() => setVenues([])); }, []);
  return (
    <table className="data-table">
      <thead><tr><th>Venue</th><th>Open</th><th>Total</th><th>SLO breaching</th><th>SLOs</th></tr></thead>
      <tbody>
        {venues.map((v) => (
          <tr key={v.venue_id}>
            <td className="mono">{v.venue_id}</td>
            <td>{v.open_incidents}</td>
            <td>{v.total_incidents}</td>
            <td>{v.slo_breaching > 0
              ? <span className="status-badge status-fail">{v.slo_breaching}</span>
              : <span className="status-badge status-ok">0</span>}</td>
            <td>{v.slo_total}</td>
          </tr>
        ))}
        {venues.length === 0 && <tr><td colSpan={5} className="muted">No venue data</td></tr>}
      </tbody>
    </table>
  );
}

function Cost() {
  const [summary, setSummary] = useState<CostSummary | null>(null);
  useEffect(() => { apiExt.getCostAnalytics().then(setSummary).catch(() => setSummary(null)); }, []);
  if (!summary) return <p className="muted">No cost data</p>;
  return (
    <div>
      <p>
        Total monthly: <strong>${summary.total_monthly_cost_usd.toLocaleString()}</strong>
        {' · '}<span className="muted">{summary.downsize_candidates} downsize, {summary.upsize_candidates} upsize candidates</span>
      </p>
      <table className="data-table">
        <thead><tr><th>Service</th><th>Monthly</th><th>CPU</th><th>Mem</th><th>Instances</th><th>Right-size</th></tr></thead>
        <tbody>
          {summary.services.map((s) => (
            <tr key={s.service_id}>
              <td>{s.service_name}</td>
              <td>${s.monthly_cost_usd.toLocaleString()}</td>
              <td>{(s.cpu_utilisation * 100).toFixed(0)}%</td>
              <td>{(s.memory_utilisation * 100).toFixed(0)}%</td>
              <td>{s.instance_count}</td>
              <td>
                <span className={`status-badge ${s.rightsizing === 'downsize' ? 'status-fail' : s.rightsizing === 'upsize' ? 'status-warn' : 'status-ok'}`}>
                  {s.rightsizing}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
