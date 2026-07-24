import { NavLink } from "react-router-dom";
import "./Sidebar.css";

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <div className="sidebar__logo">AI</div>

        <div className="sidebar__brand-text">
          <strong>Vehicle AI</strong>
          {/* <span>Танилтын систем</span> */}
        </div>
      </div>

      <nav
        className="sidebar__navigation"
        aria-label="Үндсэн цэс"
      >
        <NavLink
          to="/live"
          className={({ isActive }) =>
            isActive
              ? "sidebar__link sidebar__link--active"
              : "sidebar__link"
          }
        >
          <span className="sidebar__icon">●</span>
          <span>Live танилт</span>
        </NavLink>

        <NavLink
          to="/files"
          className={({ isActive }) =>
            isActive
              ? "sidebar__link sidebar__link--active"
              : "sidebar__link"
          }
        >
          <span className="sidebar__icon">↑</span>
          <span>Файл таних</span>
        </NavLink>

        {/* <div
          className="sidebar__link sidebar__link--disabled"
          aria-disabled="true"
        >
          <span className="sidebar__icon">◷</span>
          <span>Түүх</span>
        </div> */}
      </nav>

      <footer className="sidebar__footer">
        <span>Системийн төлөв</span>

        <div className="sidebar__system-state">
          <span className="sidebar__status-dot" />
          Ажиллаж байна
        </div>
      </footer>
    </aside>
  );
}
