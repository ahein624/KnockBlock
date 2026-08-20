#pragma once

#define KNOCKBLOCK_WIFI_SSID "your-wifi-name"
#define KNOCKBLOCK_WIFI_PASSWORD "your-wifi-password"
#define KNOCKBLOCK_HOSTNAME "kids-knockblock"

// Normally blank: the ESP32 discovers the LXC's _knockblock._tcp service.
// If multicast DNS is blocked between VLANs, use an IP such as "192.168.1.50".
#define KNOCKBLOCK_CONTROLLER_HOST ""
#define KNOCKBLOCK_CONTROLLER_PORT 5000

// Only needed when the ESP32 is not considered a local client by KnockBlock.
#define KNOCKBLOCK_API_TOKEN ""
