# Security and privacy

What it takes to run Orchard Sentinel for growers outside the team: what we protect, the standards
the industry measures itself against, what the code already does, and what to change, in order.
Written Oct 25 2026 against `master` at `ebaf08e`. Sources are at the end.

## What we protect, and from whom

| Asset | Why it matters |
| --- | --- |
| A grower's catches, biofix dates and spray timings | Commercially sensitive. Pest pressure says something about a farm's crop and practices. Under the ag-data principles below it belongs to the grower, not to us. |
| Trap locations (orchard, block, trap names) | Tells someone where the farm and its equipment are. |
| Liner photos | Mostly insects and glue. The ESP32 setup preview, or a photo taken while a liner is being changed, can show a hand, a face or the orchard. |
| Trap API keys, the hub's Wi-Fi password | With one, someone can upload fake photos and corrupt a grower's counts and spray advice. |
| The server, the hub and the team tailnet | The hub sits in a field on cellular and is on the same tailnet as the server and the team's laptops. |
| Future grower accounts (names, emails) | The only personal data in the usual sense. |

Likely attackers, most likely first: internet scanners and bots that hit any public port within minutes;
someone who walks off with a trap or the hub (physical access to flash and SD card); a careless
mistake by us (secret committed to the public repo, open dashboard, lost backup); a neighbour or
competitor curious about another grower's data; a compromised dependency or model file.

The worst outcome isn't a data leak: it's **wrong spray advice**. Fake uploads or a tampered
model could make a grower spray on the wrong day. Integrity of the counts matters as much as secrecy.

## The standards, and what we take from each

None of these is legally required of a capstone, but they're what a reviewer, a buyer or Cornell
Cooperative Extension would hold a deployed product to.

- **ETSI EN 303 645** (consumer IoT, the base of the UK PSTI law and the EU's rules) and **NIST IR 8259A**
  (US IoT baseline, the basis of the FCC's **U.S. Cyber Trust Mark**). The parts that apply to us: no
  shared default passwords; a way to report vulnerabilities; secure updates; keys stored securely;
  encrypted communication; a small attack surface; device identity; a way to delete user data.
- **OWASP ASVS 5.0, level 2** for the dashboard and **OWASP API Security Top 10 (2023)** for the
  upload API. The items that matter here: object-level authorization (a trap can only write its own
  photos), authentication, unrestricted resource use, security misconfiguration.
- **NIST SP 800-63B-4** (Aug 2025) for passwords: at least 15 characters for a password on its own,
  no forced symbols or expiry, check new passwords against breached-password lists, rate-limit guesses.
- **Ag Data Transparent Core Principles** (Farm Bureau, updated 2024): the farmer owns the data from
  their operation; tell them what's collected and why; get consent before sharing or other uses;
  let them take it out (portability) and have it deleted; say how long it's kept; never sell it.
  More than 40 ag-tech companies are certified against these. This is the one growers' lawyers know.
- **NY SHIELD Act**: anyone holding New York residents' private information must keep "reasonable
  safeguards", scaled to their size: someone in charge of security, known risks written down, data
  disposed of when no longer needed. Breach notification applies to usernames with passwords.
- **EU Cyber Resilience Act**: only if the trap is ever sold in the EU. Reporting of exploited
  vulnerabilities started Sep 11 2026; the rest applies from Dec 11 2027. Noted, not planned for.

## What we already do well

Worth keeping, and saying in the final report.

- **A key per trap, stored only as a hash.** `secrets.token_urlsafe(24)` (192 bits) and SHA-256 at
  rest ([services.py:21](../server/sentinel_server/services.py:21)). Unsalted SHA-256 is right for
  random tokens this long; it's what GitHub and Stripe do. The hub compares in constant time
  ([gateway.py:148](../device/sentinel_device/gateway.py:148)).
- **Revocable keys.** Retiring a trap returns 410, and the Set up traps page issues a new key. That's
  the incident response for a stolen trap, already built.
- **Object-level authorization on uploads.** A key can only write to its own trap: `meta.trap_id`
  must match ([app.py:135](../server/sentinel_server/app.py:135)).
- **Upload checks.** Size limits on the server and the hub, the image is parsed before it's kept,
  and the capture id is whitelisted so it can't escape `media/` (`SAFE_UID`).
- **Constant-time password check**, and `serve` warns when the dashboard has no password.
- **No secrets in the public repo.** `node_config.h`, `.env` and configs are gitignored; checked the
  tracked files and history for API keys (only the placeholder is there). The hub writes node keys
  with mode 600.
- **Tailscale between sites.** Hub → server traffic is WireGuard-encrypted, with no open ports on the
  internet.
- **Little personal data.** No accounts, no location sent anywhere, weather comes in by CSV.

## What to change

In three steps. Each item says what, why, and roughly how big it is.

### Before anyone outside the team can reach it

1. **Fail closed when there's no password.** Today an empty `SENTINEL_DASHBOARD_PASSWORD` means an
   open dashboard on `0.0.0.0` with only a warning ([cli.py:104](../server/sentinel_server/cli.py:104)).
   Refuse to start on a non-local address without one. *Small.* (ETSI 5.1, ASVS "secure defaults".)
2. **Bind to the tailnet, not every interface.** `serve` defaults to `0.0.0.0`, so the Pi 5 is
   reachable from whatever Wi-Fi or Cornell LAN it's on, not just Tailscale. Default to `127.0.0.1`
   and pass the Tailscale address (or put a proxy in front). *Small.*
3. **Tailscale access rules.** The default policy lets every device reach every other device. The
   hub is the most exposed machine we have (in a field, on cellular, its SD card removable), yet it
   can reach the server's SSH and the team's laptops. Tag machines (`tag:hub`, `tag:server`) and
   write grants: hubs → server port 8000 only; team members → everything. Tagged devices also don't
   expire with a person's login. *Small, in the admin console; keep the policy file in the repo.*
4. **Cross-site request forgery.** The dashboard uses HTTP Basic, which browsers send automatically
   with cross-site form posts, so another web page could submit a review or retire a trap in a team
   member's browser. Cheapest fix now: reject any POST whose `Origin` (or `Sec-Fetch-Site`) isn't our
   own host. *Small, one middleware.* Goes away with real sessions (step 2).
5. **Security headers** on every response: `Content-Security-Policy: default-src 'self';
   frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, and
   `Strict-Transport-Security` once on HTTPS. Check the dashboard for inline scripts before turning
   on CSP. *Small.*
6. **Turn off FastAPI's `/docs` and `/openapi.json`** in production (`docs_url=None, openapi_url=None`):
   they list every endpoint. *One line.*
7. **Rate limits**: failed passwords per IP (Basic auth can be guessed as fast as the Pi answers)
   and uploads per key. In the app, or in Caddy/Cloudflare in front. *Small to medium.*

### Before growers use it

8. **How growers reach it.** Keep Tailscale for the team, the hubs and SSH. For growers, don't open
   a port on the Pi: run **Cloudflare Tunnel** (outbound only, HTTPS, hides the Pi's address) with
   **Cloudflare Access** in front, which asks for an emailed one-time code before a request ever
   reaches our app. Free for up to 50 users. The alternative on a cloud VM is Caddy with Let's Encrypt
   and our own logins. Either way the device API (`/api/v1/*`) stays on the tailnet only. *Medium.*
9. **Accounts instead of one shared password.** Each person gets their own login, so we know who
   reviewed what, and can remove one person. Each grower sees only their own orchard's traps: add an
   `orchard_id` to traps and check it on **every** query and photo URL, including `/media/...`
   (OWASP API1, the most common API flaw). Session cookie with `HttpOnly; Secure; SameSite=Lax`, a
   CSRF token on forms, passwords per NIST 800-63B-4 (15+ chars, breached-list check, argon2id), or skip
   passwords entirely by trusting Cloudflare Access's signed identity header. *Large; the biggest item.*
10. **Server as its own user, hardened.** The server and backup units run as `pi` out of a home
    folder ([sentinel-server.service](../server/systemd/)); the device units already use a `sentinel`
    user. Add a `sentinel` user on the server too, and to every unit: `NoNewPrivileges=yes`,
    `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, `ReadWritePaths=<data dir>`. Check
    with `systemd-analyze security <unit>`. *Small; test each unit after.*
11. **Pi basics**: `unattended-upgrades` for security updates, SSH by key only (Tailscale SSH already
    is), `ufw` allowing only what each Pi serves. On the hub, make sure IP forwarding is off, so the
    cameras' access point can reach the gateway on 8080 and nothing else. *Small.*
12. **The ESP32 → hub link.** Each camera sends its API key as plain HTTP over the hub's WPA2 access
    point, so anyone with that Wi-Fi password can listen and copy keys. Switch the AP to **WPA3-SAE**
    (the ESP32-S3 supports it; passive listening no longer reveals traffic), give every hub its own AP
    password, and keep the hub firewall from step 11. Stronger later: the camera signs each request
    with an HMAC of its key instead of sending the key. *Small for WPA3.*
13. **Model files can run code.** `torch.load(..., weights_only=False)`
    ([classify.py:116](../server/sentinel_server/pipeline/classify.py:116)) and YOLO `.pt` files are
    Python pickles: a swapped file runs anything on the server. Load only weights we trained, record
    each file's SHA-256 next to it, check it on load, and prefer `weights_only=True` or safetensors.
    *Small.*
14. **Encrypted, off-site, tested backups.** Tonight's backup is an rsync of the database and photos to
    the team Mac. Use `restic` (encrypted before it leaves the Pi) to a second place too, one of them
    append-only so a compromised server can't delete its own backups, and do a restore drill each
    term. Make sure FileVault is on for the Mac. *Medium.*
15. **Repo and supply chain** (the repo is public): turn on GitHub secret scanning and push protection,
    Dependabot for pip and Actions, `permissions: contents: read` in `tests.yml`, pin actions to a commit
    SHA, commit `uv.lock` files so the Pis install what CI tested, and run `pip-audit` in CI. Pillow
    parses every upload, so its updates matter most. Give API keys a prefix (`sentinel_...`) so a pasted
    key is easy to spot by secret scanners. *Small each.*
16. **Logging that would show an attack**: failed key and password attempts, key rotations, trap
    retirements, with who and from where, kept 90 days. Alert on a burst of 401s. *Small.*

### For a product

17. **ESP32 flash encryption and Secure Boot v2.** Today anyone holding a trap can read the Wi-Fi password
    and API key out of flash with `esptool` in a minute. Espressif's production guidance is Secure Boot V2
    plus flash encryption in Release mode, with UART download mode and JTAG turned off. These burn eFuses
    and can't be undone, and they limit updates, so practice on a spare board first. Until then the
    mitigation is the revocable per-trap key: a stolen trap gets a new key on the dashboard. *Medium.*
18. **Firmware updates.** There's no over-the-air update; a fix means visiting every trap. ETSI and the
    Cyber Trust Mark both expect secure updates. The hub could serve signed images to `esp_https_ota`,
    with rollback enabled so a bad build boots the previous one. *Large.*
19. **Vulnerability reporting**: a `SECURITY.md` in the repo (GitHub's private advisory reporting) and
    `/.well-known/security.txt` (RFC 9116) on the public site, naming who answers. *Small.*
20. **Unique hub credentials at first boot**, never a shared image password (ETSI 5.1). `install-hub.sh`
    should generate the AP password and print it once. *Small.*

## Privacy

Following the Ag Data Transparent principles, in the order a grower would ask about them.

**What we collect.** Liner photos, counts and identifications, trap names and blocks, battery, temperature
and humidity, and the reviews people make. Later: account name and email. Not collected and keep it that
way: GPS coordinates, anything about people, anything from the grower's other systems. Server logs hold IP
addresses; keep them 90 days.

**Who owns it.** The grower. Say so in a one-page data agreement each cooperating grower signs before a
trap goes up, also covering the points below.

**Using it for anything else needs consent.** The one that matters to us: **photos from growers' traps are
training data for `ml/`**. Ask for that separately in the agreement (opt-in), record who agreed, and keep
non-consented photos out of `ml/data/`. Same for publishing counts in the capstone report or sharing with
Extension: aggregate or anonymize ("a Hudson Valley orchard"), unless the grower agrees to be named.

**People in photos.** Keep the setup preview stream short and local to the hub (it is today). If a photo
shows a person, leave it out of training and delete it on request.

**Taking it out.** A per-orchard export: counts and events as CSV, plus a zip of photos. The `evaluate` and
backup code already walk everything needed.

**How long we keep it.** Proposal: full photos two seasons, then delete and keep only crops and counts;
counts and biofix history as long as the grower's account exists; everything deleted within 30 days of a
request, including from backups as they age out. Write the actual numbers into the agreement.

**Never sold**, and no third-party analytics or trackers on the dashboard (there are none today).

**If something goes wrong.** One page saying who decides, how to rotate every key (dashboard per trap,
`SENTINEL_DASHBOARD_PASSWORD`, Tailscale node keys, hub AP password), and that growers whose data was
exposed are told within days. New York's law requires notice for exposed login credentials.

## Sources

Standards and guidance:
[NIST IR 8259A](https://csrc.nist.gov/pubs/ir/8259/a/final) ·
[ETSI EN 303 645](https://orrick.com/-/media/public/files/insights/2024/en_303645v020101p.pdf) ·
[FCC Cyber Trust Mark](https://www.hstoday.us/subject-matter-areas/cybersecurity/fcc-adopts-voluntary-cyber-trust-mark-labeling-rule-for-iot-devices/),
[2026 administrator change](https://www.insideglobaltech.com/2026/01/08/fcc-opens-application-window-for-new-cyber-trust-mark-program-lead-administrator/) ·
[OWASP API Security Top 10 2023](https://apisecurity.io/owasp-api-security-top-10/) ·
[OWASP ASVS index](https://cheatsheetseries.owasp.org/IndexASVS.html) ·
[OWASP HTTP headers cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet) ·
[OWASP CSRF testing](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/06-Session_Management_Testing/05-Testing_for_Cross_Site_Request_Forgery),
[PortSwigger on CSRF with Basic auth](https://portswigger.net/kb/issues/00200700_cross-site-request-forgery) ·
[NIST SP 800-63B-4 summary](https://www.enzoic.com/blog/nist-sp-800-63b-rev4/) ·
[RFC 9116 security.txt](https://www.rfc-editor.org/info/rfc9116)

Farm data and law:
[Ag Data Transparent core principles, 2024 update](https://dairyproducer.com/updated-core-principles-for-ag-data-2024-by-todd-janzen/) ·
[follow-through on the pledge](https://thecounter.org/big-ag-follow-through-farm-bureau-data-transparency-pledge/) ·
[NY SHIELD Act](https://iapp.org/news/a/new-yorks-shield-act-has-taken-effect-what-does-this-mean-for-your-business),
[small-business standard](https://irmi.com/articles/expert-commentary/the-new-york-shield-act-reasonable-security-requirement) ·
[EU CRA reporting from Sep 2026](https://www.jonesday.com/en/insights/2026/07/eu-cyber-resilience-act-24hour-reporting-duties-start-september-11-2026)

Tools and platforms:
[Espressif security overview (ESP32-S3)](https://docs.espressif.com/projects/esp-idf/en/v6.0/esp32s3/security/security.html),
[flash encryption](https://docs.espressif.com/projects/esp-idf/en/v5.4/esp32s3/security/flash-encryption.html),
[flash encryption + secure boot](https://developer.espressif.com/blog/flash-encryption-and-secure-boot/) ·
[Tailscale grants](https://tailscale.com/kb/1324/acls-grants), [hardening](https://tailscale.com/kb/1196/security-hardening) ·
[Cloudflare Tunnel vs reverse proxy](https://dev.to/merbayerp/cloudflare-tunnel-vs-reverse-proxy-ways-to-access-self-hosted-1p7b) ·
[systemd sandboxing (Arch wiki)](https://wiki.archlinux.org/title/User:NetSysFire/systemd_sandboxing) ·
[restic 3-2-1 for self-hosters](https://dev.to/byte-guard/the-3-2-1-backup-setup-for-self-hosters-restic-backblaze-b2-2mpb)
