# Security

Orchard Sentinel is a Cornell capstone project (fall 2026). The server, the hubs and the cameras
are reachable only on the team's Tailscale network, not from the internet.

## Reporting a problem

Please report a vulnerability privately: on GitHub, open the repository's **Security** tab and
choose **Report a vulnerability**. Don't open a public issue for it. We aim to reply within a week
during the semester.

Useful things to include: which part (`server/`, `device/`, `device/esp32-node/`), the commit, and
the steps to reproduce.

## What's in scope

- The server's upload API and dashboard (`server/sentinel_server/`)
- The hub gateway and the Pi camera software (`device/sentinel_device/`)
- The ESP32 camera firmware and its over-the-air updates (`device/esp32-node/`)

Model weights, datasets and the scripts in `ml/` run only on team machines and are out of scope.
