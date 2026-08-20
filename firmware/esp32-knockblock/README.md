# KnockBlock ESP32-S3 display client

This firmware drives one 64x32 HUB75 panel and displays frames rendered by a
KnockBlock controller. It is intentionally a thin client: all status logic,
fonts, images, animations, schedules, and the phone UI remain in the original
Flask application.

1. Copy `include/config.example.hpp` to `include/config.hpp` and enter the
   Wi-Fi credentials. The real file is ignored by Git.
2. Run `pio run -t upload`, then `pio device monitor`.
3. The display joins Wi-Fi as `kids-knockblock` and looks for the controller's
   `_knockblock._tcp` mDNS service.

The screen reports Wi-Fi and discovery problems directly. If mDNS cannot
cross the network, set `KNOCKBLOCK_CONTROLLER_HOST` to the controller's IP.
An API token is only necessary when the controller does not see the ESP32 as
a local-network client.

See the top-level README for wiring and panel power requirements.
