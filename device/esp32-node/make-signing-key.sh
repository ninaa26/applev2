#!/usr/bin/env bash
# Make the key that camera firmware is signed with, once for the team. release.sh signs every build with the
# private half; cameras install an update only if its signature checks out against the public half, which is
# built into them (include/firmware_key.h, committed). Keep the private key safe and backed up (a password
# manager): without it no camera can be updated over the air, and a new key reaches the cameras only by
# flashing each over USB.
#   device/esp32-node/make-signing-key.sh     # key at ~/.config/orchard-sentinel/firmware-signing.pem
set -euo pipefail
cd "$(dirname "$0")"
key=${SENTINEL_FW_SIGNING_KEY:-$HOME/.config/orchard-sentinel/firmware-signing.pem}
if [[ -e $key ]]; then echo "$key already exists: release.sh uses it. Not making another."; exit 1; fi

mkdir -p "$(dirname "$key")"
(umask 077; openssl ecparam -name prime256v1 -genkey -noout -out "$key")
pub=$(openssl ec -in "$key" -pubout 2>/dev/null)
{
  echo "// The public half of the key camera firmware is signed with (make-signing-key.sh; release.sh signs)."
  echo "// A camera installs an update only if its signature checks out against this. ECDSA P-256, SHA-256."
  echo "#pragma once"
  echo "static const char FIRMWARE_PUBKEY_PEM[] ="
  while IFS= read -r line; do echo "  \"$line\\n\""; done <<< "$pub"
  echo "  ;"
} > include/firmware_key.h

cat <<MSG
Made the firmware signing key: $key
and its public half in include/firmware_key.h. Commit that file, and back up the private key now (a
password manager): every camera flashed from here on trusts only it.
MSG
