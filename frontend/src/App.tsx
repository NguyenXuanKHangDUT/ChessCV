import {
  useEffect,
  useRef,
  useState,
} from "react";

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
import ImportPgnPage from "./pages/ImportPgnPage";

import {
  LanguageProvider,
  LanguageSwitcher,
  observeTranslatedContent,
  useLanguage,
} from "./i18n/LanguageContext";

import "./App.css";

type NavigationIcon =
  | "home"
  | "position"
  | "live"
  | "games"
  | "import"
  | "calibration";

function NavIcon({
  name,
}: {
  name: NavigationIcon;
}) {
  const shared = {
    width: 21,
    height: 21,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };

  switch (name) {
    case "home":
      return (
        <svg {...shared}>
          <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" />
          <path d="M9 21v-8h6v8" />
        </svg>
      );

    case "position":
      return (
        <svg {...shared}>
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M12 3v18M3 12h18" />
        </svg>
      );

    case "live":
      return (
        <svg {...shared}>
          <circle cx="12" cy="12" r="9" />
          <path d="m10 8 6 4-6 4Z" />
        </svg>
      );

    case "games":
      return (
        <svg {...shared}>
          <rect x="5" y="3" width="14" height="18" rx="1" />
          <path d="M9 8h6M9 12h6M9 16h4" />
        </svg>
      );

    case "import":
      return (
        <svg {...shared}>
          <path d="M12 3v12m-4-4 4 4 4-4" />
          <path d="M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" />
          <path d="M7 3H5a1 1 0 0 0-1 1v8" />
        </svg>
      );

    case "calibration":
      return (
        <svg {...shared}>
          <rect x="6" y="6" width="12" height="12" rx="1" />
          <path d="M9 1v3m6-3v3M9 20v3m6-3v3M1 9h3m-3 6h3m16-6h3m-3 6h3" />
          <path d="M10 10h4v4h-4z" />
        </svg>
      );
  }
}

const NAV_ITEMS: ReadonlyArray<{
  path: string;
  label: string;
  icon: NavigationIcon;
  end?: boolean;
}> = [
  {
    path: "/",
    label: "Home",
    icon: "home",
    end: true,
  },
  {
    path: "/position",
    label: "Position",
    icon: "position",
  },
  {
    path: "/live",
    label: "Live",
    icon: "live",
  },
  {
    path: "/games",
    label: "Games",
    icon: "games",
  },
  {
    path: "/import-pgn",
    label: "Import PGN",
    icon: "import",
  },
  {
    path: "/calibration",
    label: "Calibration",
    icon: "calibration",
  },
];

// ============================================================
// APPLICATION SHELL
//
// The language is stored globally in LanguageContext.
//
// EN / VI controls:
// - Application interface
// - Navigation labels
// - Page descriptions
// - Buttons and messages
// - Live Game voice announcements
//
// LiveGamePage consumes useLanguage() directly.
// No hidden buttons or programmatic clicks are needed.
// ============================================================

function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const {
    language,
    t,
  } = useLanguage();

  const mainRef = useRef<HTMLElement | null>(null);

  // ==========================================================
  // GLOBAL PAGE TRANSLATION
  //
  // Existing pages still contain English JSX text.
  // The shared translation observer handles that legacy text.
  //
  // The language switcher and all new components can use
  // useLanguage() / t() directly.
  // ==========================================================

  useEffect(() => {
    const main = mainRef.current;

    if (!main) {
      return;
    }

    return observeTranslatedContent(
      main,
      language,
    );
  }, [language]);

  // ==========================================================
  // RENDER
  // ==========================================================

  return (
    <div
      className={
        `app chesscv-shell${
          sidebarCollapsed ? " sidebar-collapsed" : ""
        }`
      }
    >
      {/* SIDEBAR */}

      <aside
        className="chesscv-sidebar"
        aria-label={t("Main navigation")}
      >
        {/* HEADER */}

        <div className="chesscv-sidebar-header">
          <button
            type="button"
            className="chesscv-sidebar-toggle"
            onClick={() => {
              setSidebarCollapsed((value) => !value);
            }}
            aria-label={t(
              sidebarCollapsed
                ? "Expand sidebar"
                : "Collapse sidebar",
            )}
            aria-expanded={!sidebarCollapsed}
            title={t(
              sidebarCollapsed
                ? "Expand menu"
                : "Collapse menu",
            )}
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          {!sidebarCollapsed && (
            <span className="chesscv-brand">
              ChessCV
            </span>
          )}
        </div>

        {/* NAVIGATION */}

        <nav
          className="chesscv-sidebar-nav"
          aria-label={t("Pages")}
        >
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              className={({ isActive }) =>
                `chesscv-nav-link${
                  isActive ? " active" : ""
                }`
              }
              title={
                sidebarCollapsed
                  ? t(item.label)
                  : undefined
              }
              aria-label={
                sidebarCollapsed
                  ? t(item.label)
                  : undefined
              }
            >
              <NavIcon name={item.icon} />

              {!sidebarCollapsed && (
                <span>{t(item.label)}</span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* GLOBAL LANGUAGE SWITCHER
            Always mounted, whether sidebar is expanded
            or collapsed.
        */}

        <div className="chesscv-sidebar-footer">
          <LanguageSwitcher
            collapsed={sidebarCollapsed}
          />
        </div>
      </aside>

      {/* MAIN CONTENT */}

      <main
        ref={mainRef}
        className="chesscv-main"
      >
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
            path="/import-pgn"
            element={<ImportPgnPage />}
          />

          <Route
            path="/calibration"
            element={<FixedCalibrationPage />}
          />

          <Route
            path="/players/:id"
            element={<PlayerStatsPage />}
          />
        </Routes>
      </main>
    </div>
  );
}

// ============================================================
// ROOT APPLICATION
// ============================================================

export default function App() {
  return (
    <LanguageProvider>
      <AppShell />
    </LanguageProvider>
  );
}