#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <HTTPClient.h>

#include "AudioFileSourcePROGMEM.h"
#include "AudioGeneratorMP3.h"
#include "AudioOutputI2S.h"

// ============================================================
// CHESSCV NETWORK AND I2S
// The laptop's Vite server proxies /api/voice/esp32 to FastAPI.
// No Edge TTS calls and no additional ESP32 libraries are needed.
// ============================================================

const char* WIFI_SSID = "A 312";
const char* WIFI_PASSWORD = "0833584225";

const char* LAPTOP_IP = "192.168.1.178";
const uint16_t LAPTOP_PORT = 5173;

const int I2S_BCLK = 27;
const int I2S_LRC = 26;
const int I2S_DOUT = 25;

const size_t MAX_JOB_CLIPS = 24;
const size_t MAX_MP3_BYTES = 100000;
const unsigned long POLL_INTERVAL_MS = 400;
const unsigned long ERROR_RETRY_MS = 1800;

String baseUrl;
AudioOutputI2S* audioOutput = nullptr;
AudioGeneratorMP3* decoder = nullptr;
AudioFileSourcePROGMEM* audioFile = nullptr;
uint8_t* audioBytes = nullptr;
size_t audioLength = 0;

String jobLanguage;
String jobClips[MAX_JOB_CLIPS];
unsigned long jobId = 0;
size_t jobClipCount = 0;
size_t nextClipIndex = 0;

bool hasJob = false;
bool clipPlaying = false;
bool waitingForAck = false;
unsigned long nextNetworkActionAt = 0;

// ============================================================
// AUDIO CLEANUP
// ============================================================

void cleanupAudio() {
  if (decoder != nullptr) {
    if (decoder->isRunning()) decoder->stop();
    delete decoder;
    decoder = nullptr;
  }
  if (audioFile != nullptr) {
    audioFile->close();
    delete audioFile;
    audioFile = nullptr;
  }
  if (audioBytes != nullptr) {
    free(audioBytes);
    audioBytes = nullptr;
  }
  audioLength = 0;
  clipPlaying = false;
}

void clearJob() {
  cleanupAudio();
  hasJob = false;
  waitingForAck = false;
  jobId = 0;
  jobLanguage = "";
  jobClipCount = 0;
  nextClipIndex = 0;
  for (size_t i = 0; i < MAX_JOB_CLIPS; i++) jobClips[i] = "";
}

// ============================================================
// WIFI
// ============================================================

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to WiFi");
  unsigned long began = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - began < 20000) {
    delay(350);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("Signal RSSI: ");
    Serial.println(WiFi.RSSI());
  } else {
    Serial.println("WiFi is unavailable; will reconnect.");
  }
}

// ============================================================
// FETCH A JOB:  id|vi|piece_white_knight,square_f3
//               NONE
// ============================================================

bool readNextJob() {
  WiFiClient client;
  HTTPClient http;
  String url = baseUrl + "/next";

  http.setConnectTimeout(5000);
  http.setTimeout(8000);
  if (!http.begin(client, url)) {
    Serial.println("Queue HTTP begin FAILED");
    return false;
  }

  int status = http.GET();
  if (status != HTTP_CODE_OK) {
    Serial.print("Queue HTTP status: ");
    Serial.println(status);
    http.end();
    return false;
  }

  String data = http.getString();
  http.end();
  data.trim();

  if (data == "NONE" || data.length() == 0) return false;

  int p1 = data.indexOf('|');
  int p2 = data.indexOf('|', p1 + 1);
  if (p1 < 1 || p2 <= p1 + 1) {
    Serial.print("Invalid queue response: ");
    Serial.println(data);
    return false;
  }

  unsigned long receivedJobId = data.substring(0, p1).toInt();
  String receivedLanguage = data.substring(p1 + 1, p2);
  String clipList = data.substring(p2 + 1);

  if (
    receivedJobId == 0 ||
    (receivedLanguage != "en" && receivedLanguage != "vi") ||
    clipList.length() == 0
  ) {
    Serial.println("Invalid job metadata");
    return false;
  }

  String parsed[MAX_JOB_CLIPS];
  size_t parsedCount = 0;
  int cursor = 0;

  while (cursor < (int)clipList.length()) {
    if (parsedCount >= MAX_JOB_CLIPS) {
      Serial.println("Job exceeds clip limit");
      return false;
    }

    int comma = clipList.indexOf(',', cursor);
    if (comma < 0) comma = clipList.length();
    String item = clipList.substring(cursor, comma);
    item.trim();
    if (item.length() == 0 || item.length() > 64) {
      Serial.println("Invalid clip key");
      return false;
    }

    parsed[parsedCount++] = item;
    cursor = comma + 1;
  }

  clearJob();
  jobId = receivedJobId;
  jobLanguage = receivedLanguage;
  jobClipCount = parsedCount;
  nextClipIndex = 0;
  for (size_t i = 0; i < parsedCount; i++) jobClips[i] = parsed[i];
  hasJob = true;

  Serial.println();
  Serial.print("RECEIVED JOB: ");
  Serial.print(jobId);
  Serial.print(" | language: ");
  Serial.print(jobLanguage);
  Serial.print(" | clips: ");
  Serial.println(jobClipCount);
  return true;
}

// ============================================================
// DOWNLOAD ONE MP3 COMPLETELY INTO RAM
// ============================================================

bool downloadClip(const String& key) {
  cleanupAudio();

  String url = baseUrl + "/clip/" + jobLanguage + "/" + key + ".mp3";
  Serial.print("MP3 GET: ");
  Serial.println(url);

  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(5000);
  http.setTimeout(10000);

  if (!http.begin(client, url)) {
    Serial.println("HTTP begin FAILED");
    return false;
  }

  int status = http.GET();
  if (status != HTTP_CODE_OK) {
    Serial.print("MP3 HTTP status: ");
    Serial.println(status);
    http.end();
    return false;
  }

  int contentLength = http.getSize();
  if (contentLength <= 0 || contentLength > (int)MAX_MP3_BYTES) {
    Serial.print("Invalid Content-Length: ");
    Serial.println(contentLength);
    http.end();
    return false;
  }

  audioLength = (size_t)contentLength;
  audioBytes = (uint8_t*)malloc(audioLength);
  if (audioBytes == nullptr) {
    Serial.println("MP3 allocation FAILED");
    http.end();
    cleanupAudio();
    return false;
  }

  WiFiClient* stream = http.getStreamPtr();
  size_t received = 0;
  unsigned long lastDataAt = millis();

  while (received < audioLength) {
    int available = stream->available();
    if (available > 0) {
      size_t count = (size_t)available;
      if (count > audioLength - received) count = audioLength - received;
      size_t got = stream->readBytes(audioBytes + received, count);
      if (got > 0) {
        received += got;
        lastDataAt = millis();
      }
    } else {
      if (millis() - lastDataAt > 10000) break;
      delay(2);
    }
    yield();
  }

  http.end();
  Serial.printf("MP3 bytes: %u/%u\n", (unsigned)received, (unsigned)audioLength);

  if (received != audioLength) {
    cleanupAudio();
    return false;
  }
  return true;
}

// ============================================================
// DECODE MP3 AND SEND PCM TO MAX98357A VIA I2S
// ============================================================

bool startClip(const String& key) {
  if (!downloadClip(key)) return false;

  audioFile = new AudioFileSourcePROGMEM(audioBytes, (uint32_t)audioLength);
  decoder = new AudioGeneratorMP3();
  if (audioFile == nullptr || decoder == nullptr) {
    Serial.println("MP3 decoder allocation FAILED");
    cleanupAudio();
    return false;
  }

  if (!decoder->begin(audioFile, audioOutput)) {
    Serial.println("MP3 decoder begin FAILED");
    cleanupAudio();
    return false;
  }

  clipPlaying = true;
  Serial.print("PLAYING: ");
  Serial.println(key);
  return true;
}

// ============================================================
// ACK: only after the entire announcement finished playing.
// On an HTTP failure, keep the local job and retry ACK.
// ============================================================

bool acknowledgeJob(bool success) {
  WiFiClient client;
  HTTPClient http;

  String url = baseUrl + "/ack?job_id=";
  url += jobId;
  url += success ? "&ok=true" : "&ok=false";

  http.setConnectTimeout(5000);
  http.setTimeout(8000);
  if (!http.begin(client, url)) return false;
  int status = http.POST("");
  http.end();

  Serial.print("ACK JOB ");
  Serial.print(jobId);
  Serial.print(" status: ");
  Serial.println(status);
  return status == HTTP_CODE_OK;
}

void failCurrentJob() {
  Serial.println("JOB PLAYBACK FAILED. Will retry from first clip.");
  if (WiFi.status() == WL_CONNECTED) acknowledgeJob(false);
  clearJob();
  nextNetworkActionAt = millis() + ERROR_RETRY_MS;
}

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println();
  Serial.println("ChessCV ESP32 Live Voice - offline MP3 queue");

  baseUrl = "http://";
  baseUrl += LAPTOP_IP;
  baseUrl += ":";
  baseUrl += LAPTOP_PORT;
  baseUrl += "/api/voice/esp32";
  Serial.println(baseUrl);

  connectWiFi();

  audioOutput = new AudioOutputI2S();
  if (audioOutput == nullptr ||
      !audioOutput->SetPinout(I2S_BCLK, I2S_LRC, I2S_DOUT)) {
    Serial.println("I2S initialisation FAILED");
    return;
  }
  audioOutput->SetGain(0.25f);
  Serial.println("I2S READY");
}

void loop() {
  if (audioOutput == nullptr) {
    delay(1000);
    return;
  }

  if (clipPlaying && decoder != nullptr) {
    if (decoder->isRunning()) {
      if (!decoder->loop()) {
        cleanupAudio();
        nextClipIndex++;
      }
    } else {
      cleanupAudio();
      nextClipIndex++;
    }
    yield();
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long lastReconnect = 0;
    if (millis() - lastReconnect > 3000) {
      lastReconnect = millis();
      Serial.println("WiFi reconnecting...");
      WiFi.reconnect();
    }
    delay(100);
    return;
  }

  if (millis() < nextNetworkActionAt) {
    delay(10);
    return;
  }

  if (hasJob) {
    if (waitingForAck || nextClipIndex >= jobClipCount) {
      waitingForAck = true;
      if (acknowledgeJob(true)) {
        Serial.printf("JOB %lu DONE\n", jobId);
        clearJob();
        nextNetworkActionAt = millis() + POLL_INTERVAL_MS;
      } else {
        nextNetworkActionAt = millis() + ERROR_RETRY_MS;
      }
      return;
    }

    if (!startClip(jobClips[nextClipIndex])) {
      failCurrentJob();
    }
    return;
  }

  bool received = readNextJob();
  nextNetworkActionAt = millis() + (received ? 0 : POLL_INTERVAL_MS);
  yield();
}