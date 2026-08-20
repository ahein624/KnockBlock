#include <Arduino.h>
#include <ESP32-HUB75-MatrixPanel-I2S-DMA.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <ESPmDNS.h>

#include "config.hpp"

namespace {
constexpr uint16_t kPanelWidth = 64;
constexpr uint16_t kPanelHeight = 32;
constexpr size_t kFrameBytes = kPanelWidth * kPanelHeight * 2;
constexpr unsigned long kPollMs = 125;
constexpr unsigned long kDiscoveryMs = 10000;

MatrixPanel_I2S_DMA *matrix = nullptr;
IPAddress controllerIp;
uint16_t controllerPort = KNOCKBLOCK_CONTROLLER_PORT;
String frameEtag;
unsigned long lastPoll = 0;
unsigned long lastDiscovery = 0;

void showMessage(const char *line1, const char *line2, uint16_t color) {
  matrix->clearScreen();
  matrix->setTextWrap(false);
  matrix->setTextSize(1);
  matrix->setTextColor(color);
  matrix->setCursor(2, 8);
  matrix->print(line1);
  matrix->setCursor(2, 20);
  matrix->print(line2);
  matrix->flipDMABuffer();
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(KNOCKBLOCK_HOSTNAME);
  WiFi.begin(KNOCKBLOCK_WIFI_SSID, KNOCKBLOCK_WIFI_PASSWORD);
  showMessage("WiFi", "connecting", matrix->color565(240, 180, 20));
}

bool discoverController() {
  if (strlen(KNOCKBLOCK_CONTROLLER_HOST) > 0) {
    return WiFi.hostByName(KNOCKBLOCK_CONTROLLER_HOST, controllerIp) == 1;
  }
  const int found = MDNS.queryService("knockblock", "tcp");
  if (found < 1) {
    return false;
  }
  controllerIp = MDNS.address(0);
  controllerPort = MDNS.port(0);
  Serial.printf("Controller: %s:%u\n", controllerIp.toString().c_str(), controllerPort);
  return true;
}

bool fetchFrame() {
  if (!controllerIp) {
    return false;
  }
  WiFiClient client;
  HTTPClient http;
  const String url = "http://" + controllerIp.toString() + ":" + controllerPort +
                     "/api/display/frame";
  if (!http.begin(client, url)) {
    return false;
  }
  http.setTimeout(2500);
  const char *headers[] = {"ETag"};
  http.collectHeaders(headers, 1);
  if (!frameEtag.isEmpty()) {
    http.addHeader("If-None-Match", frameEtag);
  }
  if (strlen(KNOCKBLOCK_API_TOKEN) > 0) {
    http.addHeader("Authorization", String("Bearer ") + KNOCKBLOCK_API_TOKEN);
  }

  const int status = http.GET();
  if (status == HTTP_CODE_NOT_MODIFIED) {
    http.end();
    return true;
  }
  if (status != HTTP_CODE_OK || http.getSize() != static_cast<int>(kFrameBytes)) {
    Serial.printf("Frame request failed: HTTP %d, length %d\n", status, http.getSize());
    http.end();
    return false;
  }

  WiFiClient *stream = http.getStreamPtr();
  uint8_t row[kPanelWidth * 2];
  for (uint16_t y = 0; y < kPanelHeight; ++y) {
    if (stream->readBytes(row, sizeof(row)) != sizeof(row)) {
      http.end();
      return false;
    }
    for (uint16_t x = 0; x < kPanelWidth; ++x) {
      const uint16_t pixel = (static_cast<uint16_t>(row[x * 2]) << 8) | row[x * 2 + 1];
      matrix->drawPixel(x, y, pixel);
    }
  }
  matrix->flipDMABuffer();
  frameEtag = http.header("ETag");
  http.end();
  return true;
}
}  // namespace

void setup() {
  Serial.begin(115200);
  HUB75_I2S_CFG::i2s_pins pins = {
      4, 5, 6, 7, 15, 16, 18, 8, 3, 42, -1, 40, 2, 41};
  HUB75_I2S_CFG config(kPanelWidth, kPanelHeight, 1, pins);
  config.double_buff = true;
  matrix = new MatrixPanel_I2S_DMA(config);
  if (!matrix->begin()) {
    Serial.println("HUB75 allocation failed");
    while (true) delay(1000);
  }
  matrix->setBrightness8(96);
  connectWifi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastDiscovery > kDiscoveryMs) {
      lastDiscovery = millis();
      WiFi.disconnect();
      connectWifi();
    }
    delay(25);
    return;
  }

  static bool mdnsStarted = false;
  if (!mdnsStarted) {
    mdnsStarted = MDNS.begin(KNOCKBLOCK_HOSTNAME);
    showMessage("KnockBlock", "finding server", matrix->color565(30, 180, 240));
  }
  if (!controllerIp && millis() - lastDiscovery > kDiscoveryMs) {
    lastDiscovery = millis();
    if (!discoverController()) {
      showMessage("No server", "trying again", matrix->color565(240, 80, 30));
    }
  }
  if (controllerIp && millis() - lastPoll >= kPollMs) {
    lastPoll = millis();
    if (!fetchFrame()) {
      controllerIp = IPAddress();
      frameEtag = "";
    }
  }
  delay(10);
}
