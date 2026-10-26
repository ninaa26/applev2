// The public half of the key camera firmware is signed with (make-signing-key.sh; release.sh signs).
// A camera installs an update only if its signature checks out against this. ECDSA P-256, SHA-256.
#pragma once
static const char FIRMWARE_PUBKEY_PEM[] =
  "-----BEGIN PUBLIC KEY-----\n"
  "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEjmeBvztOe1UWOhsTzOn09eP5ityG\n"
  "Fdt06Bw6fRULeSe3zRE8Z0PrTfM97NZpkqbIIXo9Mie6BS7pDFj3U0AanQ==\n"
  "-----END PUBLIC KEY-----\n"
  ;
