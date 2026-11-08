import { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { Button } from './ui';

const links = [
  { to: '/', label: 'Dashboard', roles: ['admin', 'reviewer', 'operator', 'approver'] },
  { to: '/intake', label: 'Intake', roles: ['admin', 'reviewer', 'operator'] },
  { to: '/approvals', label: 'HITL Approvals', roles: ['admin', 'approver'] },
  { to: '/agent', label: 'Agent Chat', roles: ['admin', 'reviewer', 'operator', 'approver'] },
  { to: '/rag', label: 'Knowledge Query', roles: ['admin', 'reviewer', 'operator', 'approver'] },
  { to: '/admin/docs', label: 'Admin Docs', roles: ['admin'] },
  { to: '/observability', label: 'Monitoring', roles: ['admin', 'reviewer'] },
  { to: '/audit', label: 'Audit Trail', roles: ['admin', 'reviewer', 'approver'] },
];

const NAV_KEY = 'novacure.navCollapsed';

export function AppShell() {
  const { user, logout, hasRole } = useAuth();
  const [navOpen, setNavOpen] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(() => {
    try {
      return localStorage.getItem(NAV_KEY) === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(NAV_KEY, navCollapsed ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [navCollapsed]);

  function toggleNav() {
    if (window.matchMedia('(max-width: 860px)').matches) {
      setNavOpen((v) => !v);
    } else {
      setNavCollapsed((v) => !v);
    }
  }

  const shellClass = [
    'shell',
    navOpen ? 'nav-open' : '',
    navCollapsed ? 'nav-collapsed' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={shellClass}>
      <div className="backdrop" onClick={() => setNavOpen(false)} aria-hidden />

      <header className="app-topbar">
        <button
          className="icon-btn"
          type="button"
          aria-label="Toggle navigation"
          aria-expanded={navOpen || !navCollapsed}
          onClick={toggleNav}
        >
          ☰
        </button>
        <div className="app-topbar-brand">
          <span className="brand-mark sm">N</span>
          <strong>NovaCure</strong>
        </div>
        <span className="muted app-topbar-role">{user?.role}</span>
      </header>

      <aside className="sidebar" aria-hidden={navCollapsed && !navOpen}>
        <div className="brand">
          <div className="brand-mark">N</div>
          <div className="brand-copy">
            <strong>NovaCure</strong>
            <span>Safety Intake</span>
          </div>
        </div>
        <nav>
          {links
            .filter((l) => hasRole(...(l.roles as any)))
            .map((l) => (
              <NavLink key={l.to} to={l.to} end={l.to === '/'} onClick={() => setNavOpen(false)}>
                {l.label}
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-foot">
          <div>
            <strong>{user?.full_name}</strong>
            <div className="muted">{user?.role}</div>
          </div>
          <Button variant="ghost" onClick={logout}>
            Logout
          </Button>
        </div>
      </aside>

      <main className="main">
        <div className="main-content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
