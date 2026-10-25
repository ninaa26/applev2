#!/usr/bin/env bash
# Build the camera firmware to send out from the dashboard (Set up traps → Camera firmware → Upload).
# It is the release build: no trap id or key in it, so the same file serves every camera. Raise FW_VERSION in
# src/main.cpp first: a camera installs a version only if it differs from the one it runs.
# Wi-Fi, HUB_URL and pins come from include/node_config.h, as for flashing.
set -euo pipefail
cd "$(dirname "$0")"
[[ -f include/node_config.h ]] || { echo "include/node_config.h is missing: run flash-camera.sh once to make it"; exit 1; }
pio run -e release
version=$(sed -n 's/^#define FW_VERSION "\(.*\)"/\1/p' src/main.cpp)
mkdir -p releases
cp .pio/build/release/firmware.bin "releases/firmware-$version.bin"
cat <<MSG

Firmware $version: $(pwd)/releases/firmware-$version.bin
Upload it on the dashboard (Set up traps → Camera firmware), send it to one camera, and check that camera
shows "fw $version" after its next photo before sending it to all of them.
MSG
