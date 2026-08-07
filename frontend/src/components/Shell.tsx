import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAcademy } from "../context/AcademyContext";

const primary = [
  ["/", "Home"],
  ["/demo", "Five-minute demo"],
  ["/paths", "Learning paths"],
  ["/curriculum", "Curriculum"],
  ["/dashboard", "My dashboard"],
] as const;

const explore = [
  ["/workbench", "Scenario workbench"],
  ["/contracts", "Contract explorer"],
  ["/builder", "Guided builder"],
  ["/graph", "Agent & zone graph"],
  ["/approvals", "Approval simulator"],
  ["/evidence", "Evidence explorer"],
  ["/diagnostics", "Diagnostics"],
  ["/capstone", "Capstone"],
] as const;

function AcademyMark() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true" className="academy-mark">
      <rect x="5" y="5" width="30" height="30" rx="4" />
      <path d="M12 27V13l16 14V13" />
      <circle cx="20" cy="20" r="3" />
    </svg>
  );
}

function NavigationLink({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}
    >
      <span className="nav-indicator" aria-hidden="true" />
      {label}
    </NavLink>
  );
}

export function Shell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width: 860px)").matches);
  const location = useLocation();
  const sidebarRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const previousPath = useRef(location.pathname);
  const restoreMenuFocus = useRef(false);
  const { dashboard, booting, serviceError } = useAcademy();

  useEffect(() => {
    if (previousPath.current === location.pathname) return;
    previousPath.current = location.pathname;
    restoreMenuFocus.current = false;
    setMenuOpen(false);
    requestAnimationFrame(() => document.getElementById("main-content")?.focus());
  }, [location.pathname]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 860px)");
    const update = () => {
      setMobile(media.matches);
      if (!media.matches) {
        restoreMenuFocus.current = false;
        setMenuOpen(false);
      }
    };
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (mobile && !menuOpen) sidebarRef.current?.setAttribute("inert", "");
    else sidebarRef.current?.removeAttribute("inert");
  }, [menuOpen, mobile]);
  useEffect(() => {
    if (!mobile || !menuOpen) return;
    const sidebar = sidebarRef.current;
    if (!sidebar) return;
    const focusableSelector = "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";
    const focusFirst = requestAnimationFrame(() => sidebar.querySelector<HTMLElement>(focusableSelector)?.focus());
    // Arrow const, not a hoisted `function`: a function declaration is
    // hoisted above the `if (!sidebar) return;` guard, so TypeScript cannot
    // keep `sidebar` narrowed to non-null inside it (TS18047).
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        restoreMenuFocus.current = true;
        setMenuOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...sidebar.querySelectorAll<HTMLElement>(focusableSelector)];
      if (!focusable.length) {
        event.preventDefault();
        sidebar.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      cancelAnimationFrame(focusFirst);
      document.removeEventListener("keydown", handleKeyDown);
      if (restoreMenuFocus.current && menuButtonRef.current?.isConnected) {
        restoreMenuFocus.current = false;
        requestAnimationFrame(() => menuButtonRef.current?.focus());
      }
    };
  }, [menuOpen, mobile]);

  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <header className="mobile-header">
        <NavLink to="/" className="brand brand-mobile" aria-label="Nornyx Academy home">
          <AcademyMark />
          <span>Nornyx <strong>Academy</strong></span>
        </NavLink>
        <button
          ref={menuButtonRef}
          className="menu-button"
          type="button"
          aria-expanded={menuOpen}
          aria-controls="academy-navigation"
          onClick={() => {
            if (menuOpen) restoreMenuFocus.current = true;
            setMenuOpen((value) => !value);
          }}
        >
          <span aria-hidden="true">{menuOpen ? "×" : "☰"}</span>
          <span className="sr-only">{menuOpen ? "Close navigation" : "Open navigation"}</span>
        </button>
      </header>

      {menuOpen ? <button className="nav-backdrop" tabIndex={-1} aria-label="Close navigation" onClick={() => { restoreMenuFocus.current = true; setMenuOpen(false); }} /> : null}
      <aside ref={sidebarRef} id="academy-navigation" role={mobile && menuOpen ? "dialog" : undefined} aria-modal={mobile && menuOpen ? true : undefined} aria-label={mobile && menuOpen ? "Academy navigation" : undefined} aria-hidden={mobile && !menuOpen} tabIndex={mobile && menuOpen ? -1 : undefined} className={`sidebar${menuOpen ? " sidebar-open" : ""}`}>
        <NavLink to="/" className="brand" aria-label="Nornyx Academy home">
          <AcademyMark />
          <span>Nornyx <strong>Academy</strong></span>
        </NavLink>
        <nav aria-label="Academy navigation">
          <div className="nav-group">
            <p className="nav-label">Learn</p>
            {primary.map(([to, label]) => <NavigationLink key={to} to={to} label={label} />)}
          </div>
          <div className="nav-group">
            <p className="nav-label">Explore & build</p>
            {explore.map(([to, label]) => <NavigationLink key={to} to={to} label={label} />)}
          </div>
        </nav>
        <div className="sidebar-footer">
          {dashboard ? (
            <div className="sidebar-progress">
              <div><span>Your progress</span><strong>{Math.round(dashboard.completion_percent)}%</strong></div>
              <progress className="mini-track" aria-label="Overall academy progress" max={100} value={dashboard.completion_percent}>{Math.round(dashboard.completion_percent)}%</progress>
            </div>
          ) : null}
          <NavigationLink to="/settings" label="Settings" />
          <NavigationLink to="/about" label="About & boundaries" />
        </div>
      </aside>

      <div className="app-content">
        <div className="service-strip" aria-live="polite">
          <span className={`service-light ${serviceError ? "service-offline" : booting ? "service-connecting" : "service-online"}`} />
          {booting ? "Connecting to local academy" : serviceError ? "Academy service needs attention" : "Offline-ready · inert training actions"}
        </div>
        <main id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
        <footer className="page-footer">
          <span>Nornyx Academy</span>
          <span>Governance declarations are not, by themselves, enforcement.</span>
        </footer>
      </div>
    </div>
  );
}
