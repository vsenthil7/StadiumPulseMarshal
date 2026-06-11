import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../lib/auth';

export function UserMenu() {
  const { session, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  if (!session) return null;
  const initials = session.user.email.slice(0, 2).toUpperCase();
  return (
    <div className="user-menu" ref={ref}>
      <button className="user-btn" data-testid="user-menu" onClick={() => setOpen((o) => !o)}>
        <span className="avatar">{initials}</span>
        <span className="role-badge" data-testid="role-badge">{session.user.role}</span>
      </button>
      {open && (
        <div className="user-dropdown">
          <div className="user-info">
            <div className="user-name">{session.user.fullName}</div>
            <div className="user-email mono">{session.user.email}</div>
          </div>
          <button className="user-action danger" data-testid="logout" onClick={() => logout()}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
