// The camera's side of pairing with a sealed key (sentinel_server.fleet: pairing_proof, seal_key), and the
// version order for updates. Plain C++ around one HMAC-SHA256 function, so it is checked off the board against
// the server's code (device/tests/test_firmware_pairing.py); main.cpp passes mbedtls's.
#pragma once
#include <ctype.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef void (*HmacSha256)(const uint8_t *key, size_t key_len, const uint8_t *msg, size_t len, uint8_t out[32]);

inline int fromHex(const char *hex, uint8_t *out, size_t max) {  // bytes written, or -1
  size_t n = strlen(hex);
  if (n % 2 || n / 2 > max) return -1;
  for (size_t i = 0; i < n; i += 2) {
    char pair[3] = {hex[i], hex[i + 1], 0}, *end;
    if (!isxdigit((unsigned char)pair[0]) || !isxdigit((unsigned char)pair[1])) return -1;
    out[i / 2] = (uint8_t)strtoul(pair, &end, 16);
  }
  return (int)(n / 2);
}

// fleet.pairing_proof: shows the hub and server the camera has the sticker's secret without giving it away.
inline void pairingProof(HmacSha256 hmac, const uint8_t k[32], char out[33]) {
  uint8_t mac[32];
  hmac(k, 32, (const uint8_t *)"proof", 5, mac);
  for (int i = 0; i < 16; i++) snprintf(out + 2 * i, 3, "%02x", mac[i]);
}

// The trap key the hub passed on, sealed by the server with the pairing key (fleet.seal_key): check its tag,
// which also binds it to the trap id, then decrypt it into out. False if anything doesn't check out.
inline bool openKey(HmacSha256 hmac, const uint8_t k[32], const char *id, const char *nonce_hex,
                    const char *box_hex, const char *tag_hex, char *out, size_t out_size) {
  uint8_t nonce[16], box[64], tag[16], mac[32], msg[3 + 16 + 1 + 32 + 64];
  int n_box = fromHex(box_hex, box, sizeof(box));
  size_t n_id = strlen(id), n = 0;
  if (fromHex(nonce_hex, nonce, 16) != 16 || fromHex(tag_hex, tag, 16) != 16 || n_box < 1 ||
      (size_t)n_box >= out_size || n_id > 32)
    return false;
  memcpy(msg, "tag", 3);
  n = 3;
  memcpy(msg + n, nonce, 16);
  n += 16;
  msg[n++] = (uint8_t)n_id;
  memcpy(msg + n, id, n_id);
  n += n_id;
  memcpy(msg + n, box, n_box);
  n += n_box;
  hmac(k, 32, msg, n, mac);
  uint8_t diff = 0;
  for (int i = 0; i < 16; i++) diff |= mac[i] ^ tag[i];
  if (diff) return false;
  for (int i = 0; i < n_box; i += 32) {
    uint8_t in[3 + 16 + 1];
    memcpy(in, "enc", 3);
    memcpy(in + 3, nonce, 16);
    in[19] = (uint8_t)(i / 32);
    hmac(k, 32, in, sizeof(in), mac);
    for (int j = 0; j < 32 && i + j < n_box; j++) out[i + j] = (char)(box[i + j] ^ mac[j]);
  }
  out[n_box] = 0;
  for (int i = 0; i < n_box; i++)  // the server's keys are secrets.token_urlsafe
    if (!isalnum((unsigned char)out[i]) && out[i] != '-' && out[i] != '_') return false;
  return true;
}

// a > b for dotted version numbers ("0.10.0" > "0.9.2"): a camera only ever moves to a newer version.
inline bool newerVersion(const char *a, const char *b) {
  while (*a || *b) {
    char *end;
    long x = strtol(a, &end, 10);
    a = end;
    long y = strtol(b, &end, 10);
    b = end;
    if (x != y) return x > y;
    while (*a && *a != '.') a++;
    while (*b && *b != '.') b++;
    if (*a == '.') a++;
    if (*b == '.') b++;
  }
  return false;
}
