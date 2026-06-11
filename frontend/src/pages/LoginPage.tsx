// Demo-seed sign-in. Tries LIVE /api/v1/auth/login, falls back to in-app seed
// auth offline. Quick-fill chips cover the role × 2-venue matrix so any persona
// is one click away. Mirrors the SpoofVane login, adapted to matchday venues
// and this app's four roles.
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../lib/auth';
import { DEMO_PASSWORD, DEMO_USERS } from '../lib/demo-users';
import { systemApi } from '../api/client';

export function LoginPage() {
  const { login, loading, source } = useAuth();
  const [email, setEmail] = useState('operator@arena-north.demo');
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [error, setError] = useState<string | null>(null);
  const [ssoEnabled, setSsoEnabled] = useState(false);

  useEffect(() => {
    systemApi.oidcStatus().then((s) => setSsoEnabled(s.enabled)).catch(() => setSsoEnabled(false));
  }, []);

  const grouped = useMemo(() => {
    const g: Record<string, typeof DEMO_USERS> = {};
    for (const u of DEMO_USERS) {
      const key = u.email.split('@')[1].replace('.demo', '');
      (g[key] ??= []).push(u);
    }
    return g;
  }, []);

  async function submit() {
    setError(null);
    const r = await login(email, password);
    if (!r.ok) setError(r.error ?? 'Login failed');
    // On success the app re-renders into the shell automatically (session set).
  }

  return (
    <div className="login">
      <div className="login-brand">
        <div className="login-mark">SP</div>
        <h1>StadiumPulse Marshal</h1>
        <p className="login-tagline">
          AIOps matchday operations. Detect, correlate and remediate venue
          incidents before kickoff — every action role-gated and audited.
        </p>
        <div className="login-phases">
          {['Detect', 'Correlate', 'Triage', 'Approve', 'Remediate'].map((s) => (
            <span key={s} className="phase-chip">{s}</span>
          ))}
        </div>
        <div className="login-mode">
          {source === 'seed' ? 'OFFLINE DEMO · seed identity' : 'LIVE · backend auth'}
        </div>
      </div>

      <div className="login-card-wrap">
        <div className="login-card">
          <h2>Sign in</h2>
          <label className="fld-label">Email</label>
          <input
            className="fld"
            data-testid="login-email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            autoComplete="username"
          />
          <label className="fld-label">Password</label>
          <input
            className="fld"
            data-testid="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            autoComplete="current-password"
          />
          {error && <div className="login-error" data-testid="login-error">{error}</div>}
          <button className="btn-primary login-submit" data-testid="login-submit" onClick={submit} disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>

          {ssoEnabled && (
            <a
              className="btn-sso"
              data-testid="login-sso"
              href="/api/v1/auth/oidc/login?return_to=/"
            >
              Sign in with SSO
            </a>
          )}

          <div className="login-demo">
            <div className="login-demo-head">Demo accounts · password {DEMO_PASSWORD}</div>
            {Object.entries(grouped).map(([venue, users]) => (
              <div key={venue} className="login-demo-group">
                <div className="login-demo-venue">{venue.replace(/-/g, ' ')}</div>
                <div className="login-chips">
                  {users.map((u) => (
                    <button
                      key={u.email}
                      data-testid={`quickfill-${u.role}`}
                      className={`chip ${email === u.email ? 'chip-active' : ''}`}
                      title={u.email}
                      onClick={() => { setEmail(u.email); setPassword(DEMO_PASSWORD); setError(null); }}
                    >
                      {u.role}{u.multiVenue ? ' ·multi' : ''}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
