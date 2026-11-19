
import {
  LIVE_GAME_DEBUG_STREAM_URL,
} from "../api/liveGame";

export type SpeechLanguage = "en" | "vi";

// ============================================================
// AUDIO OUTPUT ADAPTER
//
// Common interface for all audio output devices.
//
// Current:
// BrowserAudioOutputAdapter -> Laptop speakers
//
// Future:
// Esp32AudioOutputAdapter -> ESP32 + MAX98357A
// ============================================================

export interface AudioOutputAdapter {
  play(
    audio: Blob,
    signal: AbortSignal,
  ): Promise<void>;

  stop(): void;
}

// ============================================================
// BROWSER AUDIO OUTPUT
//
// Plays MP3 through the browser's normal audio output.
// Windows default audio device will be used.
// ============================================================

export class BrowserAudioOutputAdapter
  implements AudioOutputAdapter {

  private activeAudio: HTMLAudioElement | null = null;

  async play(
    audioBlob: Blob,
    signal: AbortSignal,
  ): Promise<void> {

    if (signal.aborted) {
      return;
    }

    if (!audioBlob.size) {
      throw new Error("Audio data is empty.");
    }

    const objectUrl = URL.createObjectURL(audioBlob);

    const audio = new Audio(objectUrl);

    audio.preload = "auto";

    this.activeAudio = audio;

    try {

      await new Promise<void>((resolve, reject) => {

        let completed = false;

        function finish(error?: Error): void {

          if (completed) {
            return;
          }

          completed = true;

          audio.pause();

          audio.removeEventListener(
            "ended",
            onEnded,
          );

          audio.removeEventListener(
            "error",
            onError,
          );

          signal.removeEventListener(
            "abort",
            onAbort,
          );

          if (error) {
            reject(error);
          } else {
            resolve();
          }
        }

        function onEnded(): void {
          finish();
        }

        function onError(): void {
          finish(
            new Error("MP3 playback failed."),
          );
        }

        function onAbort(): void {
          finish();
        }

        audio.addEventListener(
          "ended",
          onEnded,
        );

        audio.addEventListener(
          "error",
          onError,
        );

        signal.addEventListener(
          "abort",
          onAbort,
          { once: true },
        );

        if (signal.aborted) {
          onAbort();
          return;
        }

        void audio.play().catch(
          (error: unknown) => {

            if (signal.aborted) {
              finish();
              return;
            }

            finish(
              error instanceof Error
                ? error
                : new Error(
                    "Could not play audio on the laptop.",
                  ),
            );
          },
        );
      });

    } finally {

      audio.pause();

      audio.removeAttribute("src");

      audio.load();

      URL.revokeObjectURL(objectUrl);

      if (this.activeAudio === audio) {
        this.activeAudio = null;
      }
    }
  }

  stop(): void {

    if (!this.activeAudio) {
      return;
    }

    this.activeAudio.pause();

    this.activeAudio.currentTime = 0;
  }
}

// ============================================================
// ACTIVE AUDIO OUTPUT
//
// THIS IS THE ONLY LINE THAT NEEDS TO CHANGE
// WHEN SWITCHING FROM LAPTOP TO ESP32.
//
// Current:
// BrowserAudioOutputAdapter
//
// Future:
// Esp32AudioOutputAdapter
// ============================================================

const audioOutputAdapter: AudioOutputAdapter =
  new BrowserAudioOutputAdapter();

// ============================================================
// NEURAL TTS API
//
// Both English and Vietnamese use:
//
// Backend Edge TTS
// -> MP3
// -> Audio Output Adapter
//
// The selected language only determines the neural voice.
// ============================================================

const API_BASE_URL =
  LIVE_GAME_DEBUG_STREAM_URL.replace(
    /\/live\/debug-stream\/?$/,
    "",
  );

const NEURAL_VOICE_URL =
  `${API_BASE_URL}/voice/speak`;

// ============================================================
// GENERATE AND PLAY SPEECH
// ============================================================

export async function playNeuralSpeech(
  text: string,
  language: SpeechLanguage,
  signal: AbortSignal,
): Promise<void> {

  if (!text || signal.aborted) {
    return;
  }

  const response = await fetch(
    NEURAL_VOICE_URL,
    {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
      },

      body: JSON.stringify({
        text,
        language,
      }),

      signal,
    },
  );

  if (!response.ok) {

    let message =
      `Neural voice request failed (${response.status}).`;

    try {

      const result: unknown =
        await response.json();

      if (
        result &&
        typeof result === "object" &&
        "detail" in result &&
        typeof result.detail === "string"
      ) {
        message = result.detail;
      }

    } catch {
      // Keep the HTTP error message.
    }

    throw new Error(message);
  }

  const audioBlob =
    await response.blob();

  if (signal.aborted) {
    return;
  }

  if (!audioBlob.size) {
    throw new Error(
      "Neural voice returned empty audio.",
    );
  }

  await audioOutputAdapter.play(
    audioBlob,
    signal,
  );
}

// ============================================================
// STOP AUDIO
// ============================================================

export function stopNeuralSpeech(): void {
  audioOutputAdapter.stop();
}
