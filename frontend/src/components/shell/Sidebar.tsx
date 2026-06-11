import { NAV_GROUPS, NAV_PAGES, type NavPage } from '../../lib/nav';
import { ROLE_RANK, type Role } from '../../lib/rbac';

// Grouped, role-gated, collapsible navigation rail. Pages above the user's role
// are hidden; groups with no visible items disappear entirely.
export function Sidebar({
  role,
  activeTab,
  collapsed,
  onSelect,
  onToggle,
}: {
  role: Role;
  activeTab: string;
  collapsed: boolean;
  onSelect: (tab: string) => void;
  onToggle: () => void;
}) {
  const visible = NAV_PAGES.filter((p) => ROLE_RANK[role] >= ROLE_RANK[p.minRole]);
  return (
    <aside className="rail" data-testid="sidebar-rail" data-collapsed={collapsed ? 'true' : 'false'}>
      <div className="rail-brand">
        <span className="mark">SP</span>
        {!collapsed && (
          <div className="rail-brand-text">
            StadiumPulse
            <div className="sub">Marshal · T6</div>
          </div>
        )}
        <button
          className="rail-toggle"
          data-testid="sidebar-toggle"
          aria-label="Toggle sidebar"
          onClick={onToggle}
        >
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      {NAV_GROUPS.map((group) => {
        const items = visible.filter((p) => p.group === group);
        if (items.length === 0) return null;
        return (
          <div className="rail-group" key={group} data-testid={`nav-group-${group}`}>
            {!collapsed && <div className="rail-group-label">{group}</div>}
            <nav>
              {items.map((p: NavPage) => (
                <button
                  key={p.id}
                  className={`rail-item ${activeTab === p.tab ? 'active' : ''}`}
                  data-testid={`nav-${p.tab}`}
                  title={collapsed ? p.title : undefined}
                  onClick={() => onSelect(p.tab)}
                >
                  <span className="rail-ico" aria-hidden>{p.icon}</span>
                  {!collapsed && <span className="rail-label">{p.title}</span>}
                </button>
              ))}
            </nav>
          </div>
        );
      })}
    </aside>
  );
}
