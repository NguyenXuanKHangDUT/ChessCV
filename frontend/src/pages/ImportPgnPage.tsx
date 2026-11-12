import { useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  importPgn,
  previewPgn,
} from "../api/pgnImport";
import type { PgnImportResult, PgnPreview } from "../api/pgnImport";

import "./ImportPgnPage.css";

const MAX_PGN_CHARS = 250_000;

const SAMPLE_PGN = `[Event "Casual Game"]
[Site "Local"]
[Date "2026.11.13"]
[Round "1"]
[White "White Player"]
[Black "Black Player"]
[Result "1-0"]
[WhiteElo "1800"]
[BlackElo "1800"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6?? 4. Qxf7# 1-0`;

export default function ImportPgnPage() {
  const [pgnText, setPgnText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [preview, setPreview] = useState<PgnPreview | null>(null);
  const [result, setResult] = useState<PgnImportResult | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function changePgn(text: string, selectedFile: string | null = null) {
    requestVersion.current += 1;
    setPgnText(text);
    setFileName(selectedFile);
    setPreview(null);
    setResult(null);
    setError(null);
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (file.size > MAX_PGN_CHARS * 4) {
      setError("This PGN file is too large (maximum 250,000 characters).");
      return;
    }

    try {
      const content = await file.text();
      if (content.length > MAX_PGN_CHARS) {
        setError("This PGN contains more than 250,000 characters.");
        return;
      }
      changePgn(content, file.name);
    } catch {
      setError("Could not read the selected PGN file.");
    }
  }

  async function handlePreview(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (loadingPreview || importing) return;
    if (!pgnText.trim()) {
      setError("Paste one game PGN or select a .pgn file first.");
      return;
    }
    const version = requestVersion.current;
    setLoadingPreview(true);
    setError(null);
    setResult(null);
    try {
      const parsed = await previewPgn(pgnText);
      if (version === requestVersion.current) setPreview(parsed);
    } catch (cause) {
      if (version === requestVersion.current) {
        setPreview(null);
        setError(cause instanceof Error ? cause.message : "Could not preview PGN.");
      }
    } finally {
      setLoadingPreview(false);
    }
  }

  async function handleImport() {
    if (!preview || importing || loadingPreview) return;
    setImporting(true);
    setError(null);
    try {
      const imported = await importPgn(pgnText);
      setResult(imported);
      setPreview(imported);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not import PGN.");
    } finally {
      setImporting(false);
    }
  }

  const busy = loadingPreview || importing;
  const kept = preview ? Object.entries(preview.headers_kept) : [];
  const databaseFields = preview ? Object.entries(preview.headers_database) : [];

  return (
    <div className="page pgn-import-page">
      <div className="pgn-import-header">
        <div>
          <h1>Import PGN</h1>
          <p className="page-description">
            Add one chess game to your Games library. ChessCV validates every
            move, filters PGN headers and prepares the game for Replay / Analyze.
          </p>
        </div>
        <Link className="pgn-import-games-link" to="/games">
          View Games
        </Link>
      </div>

      {error && <div className="error-message pgn-import-error" role="alert">{error}</div>}

      <div className="pgn-import-layout">
        <form className="pgn-import-panel" onSubmit={(event) => void handlePreview(event)}>
          <div className="pgn-import-panel-top">
            <div>
              <h2>One game PGN</h2>
              <p>Paste a PGN or select a file from your computer.</p>
            </div>
            <button
              className="pgn-import-file-button"
              type="button"
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
            >
              Choose .pgn file
            </button>
            <input
              ref={fileInputRef}
              className="pgn-import-hidden-input"
              type="file"
              accept=".pgn,.txt,text/plain"
              aria-label="Choose a PGN file"
              onChange={(event) => void handleFileChange(event)}
            />
          </div>

          {fileName && <p className="pgn-import-filename">Loaded: {fileName}</p>}

          <label htmlFor="pgn-import-content" className="pgn-import-label">
            PGN content
          </label>
          <textarea
            id="pgn-import-content"
            className="pgn-import-textarea"
            spellCheck={false}
            value={pgnText}
            disabled={importing}
            maxLength={MAX_PGN_CHARS}
            placeholder={'[Event "..."]\n[White "..."]\n[Black "..."]\n[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nc6 ...'}
            onChange={(event) => changePgn(event.target.value)}
          />

          <div className="pgn-import-help">
            <span>{pgnText.length.toLocaleString()} / {MAX_PGN_CHARS.toLocaleString()} characters</span>
            <span>One PGN per import · mainline moves only</span>
          </div>

          <div className="pgn-import-actions">
            <button type="submit" className="pgn-import-preview-button" disabled={busy || !pgnText.trim()}>
              {loadingPreview ? "Validating..." : "Preview PGN"}
            </button>
            <button type="button" className="pgn-import-commit-button" disabled={busy || !preview || !!result} onClick={() => void handleImport()}>
              {importing ? "Importing..." : "Import to Games"}
            </button>
            <button type="button" className="pgn-import-clear-button" disabled={busy} onClick={() => changePgn("")}>
              Clear
            </button>
          </div>

          {!pgnText && (
            <button type="button" className="pgn-import-example" onClick={() => changePgn(SAMPLE_PGN)}>
              Load sample PGN
            </button>
          )}
        </form>

        <aside className="pgn-import-info">
          <section className="pgn-import-panel">
            <h2>Automatic header filtering</h2>
            <p>
              The stored PGN keeps Event, Date, Round, White, Black and Result.
              For custom starting positions it also keeps SetUp and FEN.
            </p>
            <p>
              ECO and Opening are saved into the Games database columns.
              Extra tags such as Site, WhiteElo, BlackElo, TimeControl and
              Annotator are omitted from the stored PGN.
            </p>
            <div className="pgn-import-info-note">
              ChessCV also generates SAN, UCI and the before/after FEN for every
              move, making replay possible without the original file.
            </div>
          </section>

          {preview && (
            <section className="pgn-import-panel pgn-import-preview" aria-live="polite">
              <div className="pgn-import-preview-top">
                <h2>Validated game</h2>
                <span className="pgn-import-valid">Valid PGN</span>
              </div>
              <div className="pgn-import-match">
                <strong>{preview.white}</strong>
                <span>vs</span>
                <strong>{preview.black}</strong>
                <b>{preview.result}</b>
              </div>
              <div className="pgn-import-stats">
                <div><strong>{preview.total_plies}</strong><span>Half-moves</span></div>
                <div><strong>{preview.total_moves}</strong><span>Move number</span></div>
                <div><strong>{preview.eco_code ?? "—"}</strong><span>ECO</span></div>
              </div>
              {preview.opening && <p className="pgn-import-opening">Opening: {preview.opening}</p>}
              {!preview.analysis_supported && (
                <p className="pgn-import-warning">
                  Replay will work. Current Stockfish Game Review is limited to 400 half-moves.
                </p>
              )}

              <h3>Kept in PGN</h3>
              <div className="pgn-import-tag-list">
                {kept.map(([name, value]) => <span key={name} title={`${name}: ${value}`}>{name}</span>)}
              </div>

              <h3>Saved in database fields</h3>
              <div className="pgn-import-tag-list">
                {databaseFields.length
                  ? databaseFields.map(([name]) => <span key={name}>{name}</span>)
                  : <span className="pgn-import-none">No ECO / Opening supplied or recognized</span>}
              </div>

              <h3>Excluded headers</h3>
              {preview.headers_removed.length ? (
                <div className="pgn-import-tag-list removed">
                  {preview.headers_removed.map((name) => <span key={name}>{name}</span>)}
                </div>
              ) : <p className="pgn-import-none">No extra headers.</p>}
              <details className="pgn-import-normalized">
                <summary>Show cleaned PGN</summary>
                <pre>{preview.normalized_pgn}</pre>
              </details>
            </section>
          )}

          {result && (
            <section className="pgn-import-panel pgn-import-success" role="status">
              <h2>{result.duplicate ? "Game already in library" : "PGN imported successfully"}</h2>
              <p>
                {result.duplicate
                  ? "An identical game was found. No duplicate was created."
                  : "The game and all its moves are now saved in ChessCV MySQL."}
              </p>
              <Link className="pgn-import-open-game" to={`/games/${result.game_id}`}>
                Open Game #{result.game_id} · Replay / Analyze
              </Link>
            </section>
          )}
        </aside>
      </div>

    </div>
  );
}