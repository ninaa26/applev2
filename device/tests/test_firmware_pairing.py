"""The camera's side of pairing (esp32-node/include/pairing.h), compiled for this computer and checked against
the server's test vector (server/tests/test_fleet.py VECTOR, made by sentinel_server.fleet.seal_key)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
INCLUDE = HERE.parent / "esp32-node" / "include"
VECTOR = {"trap_id": "T2", "api_key": "Zq3_x-9aLmN0pQrStUvWxYz1234567AB",
          "k": "f938e0516a199712e6091a4906609800722f5610dcc548220eed9e2d95d61701",
          "proof": "0c41d2eb390a2c08236aee5937d044fc", "nonce": "000102030405060708090a0b0c0d0e0f",
          "box": "787b8850ced2e9c63d4284e01254a1c3cb957ce7ebbe75ab752c48511344f7a1",
          "tag": "23e2d61862665a378994a28131013414"}

HARNESS = r"""
#include "pairing.h"
#ifdef __APPLE__
#include <CommonCrypto/CommonHMAC.h>
static void hmac(const uint8_t *key, size_t kl, const uint8_t *msg, size_t len, uint8_t out[32]) {
  CCHmac(kCCHmacAlgSHA256, key, kl, msg, len, out);
}
#else
#include <openssl/hmac.h>
static void hmac(const uint8_t *key, size_t kl, const uint8_t *msg, size_t len, uint8_t out[32]) {
  unsigned int n = 32;
  HMAC(EVP_sha256(), key, (int)kl, msg, len, out, &n);
}
#endif
int main(int argc, char **argv) {
  if (!strcmp(argv[1], "newer")) { puts(newerVersion(argv[2], argv[3]) ? "1" : "0"); return 0; }
  uint8_t k[32];
  if (fromHex(argv[2], k, 32) != 32) return 2;
  if (!strcmp(argv[1], "proof")) { char p[33]; pairingProof(hmac, k, p); puts(p); return 0; }
  char key[65];
  puts(openKey(hmac, k, argv[3], argv[4], argv[5], argv[6], key, sizeof(key)) ? key : "REFUSED");
  return 0;
}
"""


@pytest.fixture(scope="module")
def harness(tmp_path_factory) -> Path:
    cxx = shutil.which("c++")
    if cxx is None:
        pytest.skip("no C++ compiler")
    d = tmp_path_factory.mktemp("pairing")
    (d / "h.cpp").write_text(HARNESS)
    libs = [] if sys.platform == "darwin" else ["-lcrypto"]
    r = subprocess.run([cxx, "-std=c++17", "-Wall", "-Werror", "-I", str(INCLUDE), str(d / "h.cpp"), "-o", str(d / "h"), *libs],
                       capture_output=True, text=True)
    if r.returncode != 0:
        (d / "t.cpp").write_text("int main() { return 0; }\n")
        if subprocess.run([cxx, str(d / "t.cpp"), "-o", str(d / "t")], capture_output=True).returncode != 0:
            pytest.skip(f"this computer's C++ compiler can't build programs at all: {r.stderr.splitlines()[0][:120]}")
        if sys.platform != "darwin" and "openssl" in r.stderr:
            pytest.skip("no OpenSSL headers to build the check against")
        pytest.fail(r.stderr)
    return d / "h"


def run(harness: Path, *args: str) -> str:
    return subprocess.run([str(harness), *args], capture_output=True, text=True, check=True).stdout.strip()


def test_the_camera_opens_the_key_the_server_sealed(harness):
    v = VECTOR
    assert run(harness, "proof", v["k"]) == v["proof"]
    assert run(harness, "open", v["k"], v["trap_id"], v["nonce"], v["box"], v["tag"]) == v["api_key"]


def test_a_sealed_key_that_was_changed_or_meant_for_another_trap_is_refused(harness):
    v = VECTOR
    flipped = ("0" if v["box"][0] != "0" else "1") + v["box"][1:]
    other_k = "00" + v["k"][2:]
    for args in [(v["k"], "T9", v["nonce"], v["box"], v["tag"]),       # another trap id
                 (v["k"], v["trap_id"], v["nonce"], flipped, v["tag"]),  # changed on the way
                 (other_k, v["trap_id"], v["nonce"], v["box"], v["tag"]),  # another camera's secret
                 (v["k"], v["trap_id"], v["nonce"][:-2], v["box"], v["tag"]),
                 (v["k"], v["trap_id"], v["nonce"], "zz", v["tag"])]:
        assert run(harness, "open", *args) == "REFUSED"


def test_a_camera_only_moves_to_a_newer_firmware_version(harness):
    for a, b, newer in [("0.4.0", "0.3.0", True), ("0.10.0", "0.9.2", True), ("0.3.0", "0.4.0", False),
                        ("0.4.0", "0.4.0", False), ("1.0", "0.9.9", True), ("0.4.1", "0.4", True), ("0.4", "0.4.0", False)]:
        assert run(harness, "newer", a, b) == ("1" if newer else "0"), (a, b)
