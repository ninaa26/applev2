#!/usr/bin/env bash
# Build the camera firmware to send out from the dashboard (Set up traps → Camera firmware → Upload).
# It is the release build: no trap id or key in it, so the same file serves every camera. Raise FW_VERSION in
# src/main.cpp first: a camera installs a version only if it differs from the one it runs.
# Wi-Fi, HUB_URL and pins come from include/node_config.h, as for flashing.
# The build is tagged fw-<version> (pushed to GitHub when the commit is on origin/master), so each firmware
# version can be traced to its code. The .bin itself holds the Wi-Fi password: it stays out of git.
set -euo pipefail
cd "$(dirname "$0")"
[[ -f include/node_config.h ]] || { echo "include/node_config.h is missing: run flash-camera.sh once to make it"; exit 1; }
pio run -e release
version=$(sed -n 's/^#define FW_VERSION "\(.*\)"/\1/p' src/main.cpp)
mkdir -p releases
cp .pio/build/release/firmware.bin "releases/firmware-$version.bin"
tag=fw-$version
if [[ -n $(git status --porcelain -- .) ]]; then
  echo "note: esp32-node/ has uncommitted changes, so $tag is not tagged; commit, then build again"
elif [[ -n $(git tag -l "$tag") ]]; then
  [[ $(git rev-parse "$tag^{commit}") == $(git rev-parse HEAD) ]] \
    || echo "note: $tag already names another commit: raise FW_VERSION in src/main.cpp"
else
  git tag -a "$tag" -m "camera firmware $version" HEAD
  if git fetch -q origin master 2>/dev/null; git merge-base --is-ancestor HEAD origin/master; then
    git push -q origin "$tag" || echo "note: could not push tag $tag; push it later with: git push origin $tag"
  else
    echo "tagged $tag here only: the commit isn't on origin/master"
  fi
fi

cat <<MSG

Firmware $version: $(pwd)/releases/firmware-$version.bin
Upload it on the dashboard (Set up traps → Camera firmware), send it to one camera, and check that camera
shows "fw $version" after its next photo before sending it to all of them.
MSG
