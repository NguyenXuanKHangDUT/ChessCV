import { useState } from "react";

import {
  NavLink,
  Route,
  Routes,
} from "react-router-dom";

import HomePage from "./pages/HomePage";

import UploadPositionPage from "./pages/UploadPositionPage";

import LiveGamePage from "./pages/LiveGamePage";

import GamesPage from "./pages/GamesPage";

import GameDetailPage from "./pages/GameDetailPage";

import PlayerStatsPage from "./pages/PlayerStatsPage";

import FixedCalibrationPage from "./pages/FixedCalibrationPage";


export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div
      className={
        `app${sidebarCollapsed ? " sidebar-collapsed" : ""}`
      }
    >
      <header className="topbar">

        {/* SIDEBAR HEADER / TOGGLE */}

        <div className="sidebar-top">

          <button
            type="button"
            className="sidebar-toggle"
            onClick={() =>
              setSidebarCollapsed((value) => !value)
            }
            aria-label={
              sidebarCollapsed
                ? "Expand sidebar"
                : "Collapse sidebar"
            }
            aria-expanded={!sidebarCollapsed}
            title={
              sidebarCollapsed
                ? "Expand menu"
                : "Collapse menu"
            }
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path
                d="M4 6h16M4 12h16M4 18h16"
                strokeLinecap="round"
              />
            </svg>
          </button>

          <div className="brand">
            <span className="brand-full">
              ChessCV
            </span>
            <span className="brand-mini">
              CV
            </span>
          </div>

        </div>


        {/* NAVIGATION */}

        <nav
          className="sidebar-nav"
          aria-label="Main navigation"
        >

          <NavLink
            to="/"
            end
            title="Home"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <path
                d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zM9 21v-8h6v8"
                strokeLinejoin="round"
              />
            </svg>

            <span className="nav-label">
              Home
            </span>
          </NavLink>


          <NavLink
            to="/position"
            title="Position"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <rect
                x="3"
                y="3"
                width="18"
                height="18"
                rx="2"
              />
              <path d="M12 3v18M3 12h18" />
            </svg>

            <span className="nav-label">
              Position
            </span>
          </NavLink>


          <NavLink
            to="/live"
            title="Live"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <circle
                cx="12"
                cy="12"
                r="9"
              />
              <path
                d="m10 8 6 4-6 4z"
                strokeLinejoin="round"
              />
            </svg>

            <span className="nav-label">
              Live
            </span>
          </NavLink>


          <NavLink
            to="/games"
            title="Games"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <path
                d="M5 3h14v18H5zM9 7h6M9 11h6M9 15h4"
                strokeLinecap="round"
              />
            </svg>

            <span className="nav-label">
              Games
            </span>
          </NavLink>


          {/* FIXED BOARD CALIBRATION */}

          <NavLink
            to="/calibration"
            title="Fixed Board Calibration"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <path
                d="M8 3H4a1 1 0 0 0-1 1v4M16 3h4a1 1 0 0 1 1 1v4M3 16v4a1 1 0 0 0 1 1h4M21 16v4a1 1 0 0 1-1 1h-4"
                strokeLinecap="round"
              />
              <path
                d="M7 7h10v10H7zM12 7v10M7 12h10"
              />
            </svg>

            <span className="nav-label">
              Calibration
            </span>
          </NavLink>

        </nav>
      </header>


      {/* EXISTING ROUTES + CALIBRATION ROUTE */}

      <main>
        <Routes>

          <Route
            path="/"
            element={<HomePage />}
          />

          <Route
            path="/position"
            element={<UploadPositionPage />}
          />

          <Route
            path="/live"
            element={<LiveGamePage />}
          />

          <Route
            path="/games"
            element={<GamesPage />}
          />

          <Route
            path="/games/:id"
            element={<GameDetailPage />}
          />

          <Route
            path="/players/:id"
            element={<PlayerStatsPage />}
          />

          <Route
            path="/calibration"
            element={<FixedCalibrationPage />}
          />

        </Routes>
      </main>

    </div>
  );
}