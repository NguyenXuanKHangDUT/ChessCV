/**
 * ChessCV offline voice output: laptop speaker or ESP32/MAX98357A.
 *
 * Both destinations use the same 224 fixed MP3 clips, without live Edge TTS.
 * In ESP32 mode, clip keys are queued in FastAPI; ESP32 polls the queue and
 * acknowledges only after it has played the full announcement.
 *
 * The legacy playNeuralSpeech() name is retained for LiveGamePage compatibility.
 */

import { LIVE_GAME_DEBUG_STREAM_URL } from "../api/liveGame";

export type SpeechLanguage = "en" | "vi";
export type AudioOutputMode = "laptop" | "esp32";

interface AudioClipInfo {
  key: string;
  match: string;
  speech: string;
  file: string;
}

interface AudioManifest {
  version: number;
  languages: Record<SpeechLanguage, AudioClipInfo[]>;
}

interface PreparedClip extends AudioClipInfo {
  normalizedMatch: string;
  buffer: AudioBuffer;
}

interface PreparedLanguage {
  sortedClips: PreparedClip[];
}

export interface Esp32AudioStatus {
  online: boolean;
  pending: number;
  retry_count: number;
  source: string;
}

export interface AudioOutputAdapter {
  play(buffers: AudioBuffer[], signal: AbortSignal): Promise<void>;
  stop(): void;
}

const OUTPUT_STORAGE_KEY = "chesscv.audioOutput";

export function getAudioOutputMode(): AudioOutputMode {
  if (typeof window === "undefined") return "laptop";
  try {
    return window.localStorage.getItem(OUTPUT_STORAGE_KEY) === "esp32"
      ? "esp32"
      : "laptop";
  } catch {
    return "laptop";
  }
}

export function setAudioOutputMode(mode: AudioOutputMode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(OUTPUT_STORAGE_KEY, mode);
  } catch {
    // Selection still works for this tab even when storage is disabled.
  }
  selectedOutputMode = mode;
  if (mode === "esp32") audioOutputAdapter.stop();
}

let selectedOutputMode: AudioOutputMode = getAudioOutputMode();

let sharedContext: AudioContext | null = null;

function getAudioContext(): AudioContext {
  if (typeof window === "undefined" || !window.AudioContext) {
    throw new Error("This browser does not support Web Audio.");
  }
  if (!sharedContext || sharedContext.state === "closed") {
    sharedContext = new AudioContext({ latencyHint: "interactive" });
  }
  return sharedContext;
}

export class BrowserAudioOutputAdapter implements AudioOutputAdapter {
  private activeCancel: (() => void) | null = null;

  async play(buffers: AudioBuffer[], signal: AbortSignal): Promise<void> {
    if (signal.aborted || buffers.length === 0) return;

    const context = getAudioContext();
    if (context.state !== "running") await context.resume();
    if (signal.aborted) return;
    if (context.state !== "running") {
      throw new Error("Browser audio is locked. Click Start Game to enable sound.");
    }

    this.stop();

    await new Promise<void>((resolve, reject) => {
      let completed = false;
      const sources: AudioBufferSourceNode[] = [];

      const finish = (error?: Error) => {
        if (completed) return;
        completed = true;
        signal.removeEventListener("abort", onAbort);
        for (const source of sources) {
          source.onended = null;
          try { source.stop(); } catch { /* Already stopped. */ }
          source.disconnect();
        }
        if (this.activeCancel === onAbort) this.activeCancel = null;
        if (error) reject(error);
        else resolve();
      };

      const onAbort = () => finish();
      this.activeCancel = onAbort;
      signal.addEventListener("abort", onAbort, { once: true });
      if (signal.aborted) { onAbort(); return; }

      try {
        let startAt = context.currentTime + 0.04;
        let lastSource: AudioBufferSourceNode | null = null;
        for (const buffer of buffers) {
          const source = context.createBufferSource();
          source.buffer = buffer;
          source.connect(context.destination);
          sources.push(source);
          source.start(startAt);
          startAt += buffer.duration + 0.035;
          lastSource = source;
        }
        if (lastSource) lastSource.onended = () => finish();
        else finish();
      } catch (error) {
        finish(error instanceof Error ? error : new Error("Offline playback failed."));
      }
    });
  }

  stop(): void { this.activeCancel?.(); }
}

const audioOutputAdapter: AudioOutputAdapter = new BrowserAudioOutputAdapter();

const AUDIO_BASE_URL = `${import.meta.env.BASE_URL}audio/`;
const MANIFEST_URL = `${AUDIO_BASE_URL}manifest.json`;

const API_BASE_URL = LIVE_GAME_DEBUG_STREAM_URL.replace(
  /\/live\/debug-stream\/?$/,
  "",
);
const ESP32_API_URL = `${API_BASE_URL}/voice/esp32`;

let manifestPromise: Promise<AudioManifest> | null = null;
const prepared = new Map<SpeechLanguage, PreparedLanguage>();
const preparationPromises = new Map<SpeechLanguage, Promise<void>>();

function normalizeSpeech(text: string): string {
  return text
    .normalize("NFC")
    .toLocaleLowerCase("vi-VN")
    .replace(/[.,!?;:()[\]{}"'“”]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

async function getManifest(): Promise<AudioManifest> {
  if (!manifestPromise) {
    manifestPromise = (async () => {
      const response = await fetch(MANIFEST_URL, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(
          `Offline audio manifest missing (${response.status}). Run build_offline_chess_audio.py.`,
        );
      }

      const result: unknown = await response.json();
      if (
        !result || typeof result !== "object" ||
        !("version" in result) || result.version !== 1 ||
        !("languages" in result) || !result.languages ||
        typeof result.languages !== "object" ||
        !("en" in result.languages) || !("vi" in result.languages) ||
        !Array.isArray(result.languages.en) ||
        !Array.isArray(result.languages.vi)
      ) {
        throw new Error("Invalid offline audio manifest.");
      }
      return result as AudioManifest;
    })().catch((error: unknown) => {
      manifestPromise = null;
      throw error;
    });
  }
  return manifestPromise;
}

/**
 * Validate, download and decode every clip in the selected language.
 * Start Game in LiveGamePage already calls this function.
 */
export async function prepareOfflineSpeech(language: SpeechLanguage): Promise<void> {
  if (prepared.has(language)) return;
  const existing = preparationPromises.get(language);
  if (existing) return existing;

  const promise = (async () => {
    const manifest = await getManifest();
    const entries = manifest.languages[language];
    if (!entries || entries.length === 0) {
      throw new Error(`Offline ${language.toUpperCase()} pack is empty.`);
    }

    const context = getAudioContext();
    const clips: PreparedClip[] = [];
    const matches = new Set<string>();

    for (let index = 0; index < entries.length; index += 8) {
      const batch = entries.slice(index, index + 8);
      const loaded = await Promise.all(batch.map(async (entry) => {
        if (
          typeof entry.key !== "string" ||
          typeof entry.match !== "string" ||
          typeof entry.file !== "string" ||
          typeof entry.speech !== "string" ||
          !/^[a-z0-9_]{1,64}$/.test(entry.key) ||
          !entry.file.startsWith(`${language}/`) ||
          !/^[a-z0-9_/.-]+\.mp3$/.test(entry.file)
        ) {
          throw new Error(`Invalid ${language} audio manifest entry.`);
        }

        const response = await fetch(`${AUDIO_BASE_URL}${entry.file}`, {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`Missing offline audio: ${entry.file}`);
        }
        const data = await response.arrayBuffer();
        if (data.byteLength < 600) {
          throw new Error(`Empty offline audio: ${entry.file}`);
        }
        const buffer = await context.decodeAudioData(data);
        if (buffer.duration <= 0) {
          throw new Error(`Invalid decoded audio: ${entry.file}`);
        }
        return {
          ...entry,
          normalizedMatch: normalizeSpeech(entry.match),
          buffer,
        };
      }));
      clips.push(...loaded);
    }

    for (const clip of clips) {
      if (!clip.normalizedMatch || matches.has(clip.normalizedMatch)) {
        throw new Error(`Duplicate/empty offline phrase: ${clip.match}`);
      }
      matches.add(clip.normalizedMatch);
    }

    clips.sort((a, b) => b.normalizedMatch.length - a.normalizedMatch.length);
    prepared.set(language, { sortedClips: clips });
  })();

  preparationPromises.set(language, promise);
  try { await promise; }
  finally { preparationPromises.delete(language); }
}

function parseSpeech(text: string, language: SpeechLanguage): PreparedClip[] {
  const pack = prepared.get(language);
  if (!pack) {
    throw new Error(`Offline ${language.toUpperCase()} voice pack is not ready.`);
  }

  let remaining = normalizeSpeech(text);
  const result: PreparedClip[] = [];

  while (remaining) {
    const match = pack.sortedClips.find(
      (clip) =>
        remaining === clip.normalizedMatch ||
        remaining.startsWith(`${clip.normalizedMatch} `),
    );
    if (!match) {
      throw new Error(`Offline voice lacks a clip for: "${remaining}"`);
    }
    result.push(match);
    remaining = remaining.slice(match.normalizedMatch.length).trimStart();
  }
  return result;
}

function newRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `chesscv_${crypto.randomUUID()}`;
  }
  return `chesscv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

async function enqueueEsp32Clips(
  clips: PreparedClip[],
  language: SpeechLanguage,
  signal: AbortSignal,
): Promise<void> {
  const body = JSON.stringify({
    request_id: newRequestId(),
    language,
    clips: clips.map((clip) => clip.key),
  });
  let lastError: Error = new Error("ESP32 audio queue failed.");

  for (let attempt = 1; attempt <= 3; attempt++) {
    if (signal.aborted) return;
    try {
      const response = await fetch(`${ESP32_API_URL}/enqueue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal,
      });
      if (response.ok) return;
      let details = `ESP32 queue HTTP ${response.status}`;
      try {
        const result: { detail?: string } = await response.json();
        if (typeof result.detail === "string") details = result.detail;
      } catch { /* Keep status. */ }
      lastError = new Error(details);
      if (response.status >= 400 && response.status < 500 && response.status !== 429) {
        throw lastError;
      }
    } catch (error) {
      if (signal.aborted) return;
      lastError = error instanceof Error ? error : new Error("ESP32 network failure.");
    }
    if (attempt < 3) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, 350 * attempt));
    }
  }
  throw lastError;
}

export async function getEsp32AudioStatus(): Promise<Esp32AudioStatus> {
  const response = await fetch(`${ESP32_API_URL}/status`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`ESP32 audio status HTTP ${response.status}`);
  }
  return response.json() as Promise<Esp32AudioStatus>;
}

// Compatible with the existing LiveGamePage speech queue.
export async function playNeuralSpeech(
  text: string,
  language: SpeechLanguage,
  signal: AbortSignal,
): Promise<void> {
  if (!text.trim() || signal.aborted) return;

  await prepareOfflineSpeech(language);
  if (signal.aborted) return;

  const clips = parseSpeech(text, language);
  const mode = selectedOutputMode;
  if (mode === "esp32") {
    await enqueueEsp32Clips(clips, language, signal);
  } else {
    await audioOutputAdapter.play(clips.map((clip) => clip.buffer), signal);
  }
}

export function stopNeuralSpeech(): void {
  audioOutputAdapter.stop();
}

if (typeof window !== "undefined") {
  const unlock = () => {
    try {
      const context = getAudioContext();
      if (context.state === "suspended") {
        void context.resume().catch(() => undefined);
      }
    } catch { /* Playback will report a real error when requested. */ }
  };
  window.addEventListener("pointerdown", unlock, { passive: true });
  window.addEventListener("keydown", unlock);

  let selected: SpeechLanguage = "en";
  try {
    if (window.localStorage.getItem("chesscv.language") === "vi") selected = "vi";
  } catch { /* Storage may be blocked. */ }
  void prepareOfflineSpeech(selected).catch(() => undefined);
}