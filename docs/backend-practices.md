# Python backend practices: where this repo stands

Checklist for a mostly-Python GitHub repo with a server backend, checked against `server/`
(FastAPI + SQLite) and the GitHub repo settings. Last updated Oct 25 2026.

**History.** Rounds 1–9 (Oct 25): built the list, then checked it against a generic checklist,
GitHub's "Best practices for repositories", a beginner setup tutorial, Sairyss/backend-best-practices,
DataCamp's Python backend tutorial, and three dev.to articles (repository practices, GitHub Secrets,
securing code). Round 10 (Oct 25): [PR #60](https://github.com/ninaa26/applev2/pull/60) landed
items 1, 2, 6 and 11 and was checked; this branch did items 4, 7, 8 (rate limiting), 14
(`SECURITY.md`), 15 and 16. Round 11 (Oct 25): dismissed the CodeQL alerts and set the
GitHub settings for items 10, 14 and 17. Round 12: checked Dependabot PRs #61–#63 (item 6).

## Already in place

- **Separate envs per package, made with `uv`**, and CI runs all three test suites on every PR
  ([tests.yml](../.github/workflows/tests.yml)).
- **Tests are in their own `tests/` folders** (`server/tests/` has 11 pytest files).
- **Config comes from env vars**: `server/sentinel_server/settings.py` reads a `.env` (its own small
  loader, no `python-dotenv` needed), and [server/.env.example](../server/.env.example) is committed.
- **`.gitignore` covers** `.env`, `.venv/`, `*.pyc`, data folders and `*.pt` weights.
- **No secrets in GitHub Actions.** CI only runs tests and uses no repository secrets, and the
  workflow token defaults to read-only (checked through the API). Deploys run from a team laptop
  over Tailscale, so no server or SSH key is stored on GitHub at all.
- **Keys aren't logged**: the server and hub log lines mention trap ids and pairing codes, never the
  API keys themselves.
- **GitHub secret scanning and push protection are on** (checked through the GitHub API).
- **Branch + PR workflow**, with commit subjects starting with the area. Both collaborators work
  in this one repo, with no forks, which is what GitHub recommends for a regular team.
- **The repo has a clear name and description**, and Issues are on and in use.
- **A thorough `README.md`** at the root, with details in `docs/`, `ml/README.md` and
  `hardware/CAMERAS.md`. A fresh clone can be set up from it: the README gives the `uv venv` +
  `uv pip install -e '.[dev]'` commands.
- **Logging uses the `logging` module**: there are no `print()` calls in the server package outside
  the CLI.
- **`/healthz` exists**, and both `server/deploy.sh` and `device/deploy-hub.sh` wait for it, then
  roll back if it doesn't answer.
- **SQLite runs in WAL mode** (`db.py`), and `backup.py` takes consistent snapshots and rsyncs them
  to another machine.
- **Runs as a service** (`server/systemd/`, `server/launchd/`).
- **Heavy ML dependencies are optional extras**, so the base server install stays light.
- **API is versioned** (`/api/v1/...`), so the cameras' firmware keeps working if a `/v2` is added.
- **Input limits and key handling**: photo uploads over `max_upload_mb` get a 413, firmware uploads
  are capped, trap and hub keys are stored hashed, the dashboard password is compared in constant
  time, and hub pairing codes are 10 characters from a 31-letter alphabet (about 50 bits, too many to
  guess).
- **No XSS or SQL injection found**: FastAPI's `Jinja2Templates` autoescapes by default and no
  template uses `|safe`. Queries go through SQLAlchemy with bound parameters; the only f-string SQL
  is the column-adding code in `db.py`, which uses names from `models.py`, not user input.
- **Traffic is encrypted** by Tailscale (WireGuard) between the hub, the server and the team's
  laptops, so plain HTTP inside the tailnet is fine.
- **Database indexes** are declared in `models.py` (13 `index=True` / `Index(...)`).
- **Restoring a backup is documented** in [server-on-linux.md](server-on-linux.md), and
  `deploy.sh --rollback` restores the code and database from before the last deploy.
- **One clear entry point**: the `sentinel-server` CLI (`cli.py`).

## To do, roughly most valuable first

| # | Practice | Status |
|---|----------|--------|
| 1 | Lock dependencies (`uv.lock`) | done in PR #60: `uv.lock` for `server/` and `device/`, `uv sync --locked` in CI, deploys install the locked versions |
| 2 | Linter and formatter (`ruff`) | done in PR #60: `ruff.toml` and a lint job in CI (lint only; no formatter yet) |
| 3 | Type checking (`mypy` or `pyright`) | to do |
| 4 | Pydantic models for request bodies | done: `HubPairing` and `HubClaim` models in `app.py` |
| 5 | Versioned schema migrations (Alembic) | to do |
| 6 | Dependabot + `pip-audit` | done in PR #60: `.github/dependabot.yml` (weekly uv, monthly Actions); `pip-audit` not added |
| 7 | Pre-commit hooks | done: `.pre-commit-config.yaml` (Ruff, large files, private keys); each person runs `uvx pre-commit install` once |
| 8 | Require auth on anything exposed | rate limiting done (10 wrong passwords per address per 10 min); required password + HTTPS wait for a public host |
| 9 | Ops basics | mostly done; only JSON logs are left (optional) |
| 10 | Branch protection on `master` | done Oct 25: PRs required (no approvals, so either teammate can merge their own), `lint`, `server`, `device` and `ml` must pass, no force-push or deletion; admins can still bypass in an emergency |
| 11 | GitHub Dependabot alerts + code scanning | done in PR #60: Dependabot alerts + security updates on, CodeQL default setup (Python, Actions). its 12 first-scan alerts were checked and dismissed with reasons (see below) |
| 12 | Least privilege for keys and accounts | to check |
| 13 | Add a `LICENSE` | to decide (checked: the public repo has none) |
| 14 | `SECURITY.md` + private vulnerability reporting | done: `SECURITY.md`, and private vulnerability reporting turned on Oct 25 |
| 15 | Graceful shutdown of the worker | checked, safe: each photo is one transaction and the worker writes no files, so a restart mid-photo just redoes it |
| 16 | CSRF protection + security headers on the dashboard | done: same-site check on dashboard POSTs + `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy` |
| 17 | Repo housekeeping: topics, auto-delete merged branches | done Oct 25: topics `agriculture`, `computer-vision`, `esp32`, `fastapi`, `integrated-pest-management`, `raspberry-pi`; merged branches are deleted automatically |

1. **Lock your dependencies.** [server/pyproject.toml](../server/pyproject.toml) only gives minimum
   versions (`fastapi>=0.110`), so CI and the Pi 5 can each install different versions. Commit a
   `uv.lock` (`uv lock`), then use `uv sync --frozen` in CI and in `deploy.sh`, so what you tested
   is what you deploy.
2. **Add a linter and formatter: `ruff`.** It's one tool and fast, and it replaces both `flake8` and
   `black`. Add it to `[dev]`, put `[tool.ruff]` in each pyproject, and add a `ruff check` +
   `ruff format --check` step to CI.
3. **Add type checking with `mypy` or `pyright`.** Start loose and turn it on per module. FastAPI
   and SQLAlchemy 2.0 both have good type support.
4. **Validate request bodies with Pydantic models instead of `dict`.** Endpoints like
   `api_hub_pairing(body: dict = Body(...))` in `server/sentinel_server/app.py` accept any shape.
   A `BaseModel` gives you validation, clear 422 errors and accurate `/docs` for free.
5. **Version the database schema.** Schema changes are handled by hand in
   `server/sentinel_server/db.py`. Alembic lets you upgrade the Pi 5's database safely, and moving
   to the `postgres` extra later becomes easy.
6. **Automate dependency and security updates.** Add `.github/dependabot.yml` for pip and GitHub
   Actions, and optionally run `pip-audit` in CI. GitHub's `actions/dependency-review-action` can also
   flag a PR that adds a dependency with a known vulnerability.
   The first three Dependabot PRs (Oct 25) were checked: #61 moves CI to `actions/checkout@v7` and
   `setup-uv@v7`; #62 (uvicorn) and #63 (psycopg) only raise the minimum in `pyproject.toml` to the
   version `uv.lock` already had, so nothing installed changes. They also rewrite `uv.lock` in uv's
   newer format (`revision = 5`), which the team's uv 0.12.10 reads fine.
7. **Pre-commit hooks**: a `.pre-commit-config.yaml` running ruff plus a check for large files, so
   photos or `.pt` files can't slip into a commit.
8. **Require authentication on anything exposed.** `SENTINEL_DASHBOARD_PASSWORD` is optional.
   That's fine while the server is only reachable over Tailscale, but make it required if it ever
   moves to a real cloud host. Add rate limiting to the dashboard password at the same time
   (for example a few failed tries per minute per IP); right now nothing slows down guessing. Put it
   behind HTTPS too (Caddy or `tailscale serve`/Funnel gives you a certificate), since Basic auth
   sends the password in every request.
9. **Ops basics.** Already done: `/healthz` with deploy rollback, `logging`, WAL mode and backups
   pushed off the SD card. JSON log output is the only thing left, and it's only worth adding if
   logs go to a collector.
10. **Protect `master`.** On GitHub, require the `tests` check to pass and a PR before merging. The
    API currently reports `master` as not protected.
11. **Turn on Dependabot alerts and code scanning.** Do this in the repo's Settings → Code security.
    Secret scanning and push protection are already on; Dependabot alerts and security updates are
    off, and CodeQL code scanning isn't set up. CodeQL's "default setup" is free for public repos
    like this one. Turn on **Dependabot security updates** too (a separate toggle); it opens a fix PR
    when an alert appears. Version-update PRs come from the `dependabot.yml` in item 6. CodeQL
    covers the Python and the dashboard's JavaScript; the ESP32 C++ firmware needs CodeQL's
    advanced setup with a PlatformIO build, which isn't worth it for now.
12. **Least privilege.** Check that each deploy key or SSH key opens only the machine it's for, that
    hub tokens can only post for their own trap (`hub_trap` in `app.py` appears to do this), and that
    a Postgres user, if you switch to Postgres, isn't a superuser.

13. **Add a license.** The repo is public but has no license, which legally means nobody else may
    reuse the code. Because this is a Cornell capstone, ask the course staff or sponsor whether
    they need particular terms before picking one (MIT is the usual default). Add a `CITATION.cff`
    too if you'd like people to cite the project. `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` only
    matter if outsiders start contributing.
14. **Add `SECURITY.md` and turn on private vulnerability reporting.** A short `SECURITY.md` says
    whom to contact and that the system runs only on the team Tailscale. Turn on the reporting in
    Settings → Code security; it's currently off.

15. **Shut down gracefully.** uvicorn already finishes in-flight requests on SIGTERM. Check that the
    pipeline worker does the same, so that a `systemctl restart` during a deploy doesn't leave a
    photo half-processed (it should either finish the photo or leave it queued to redo).

16. **Add CSRF protection to the dashboard's POST routes.** The dashboard has 10 form routes
    (`/traps/...`, `/tracks/.../review`, `/manage/...`), including **firmware upload**
    (`/manage/firmware`) and the firmware target. A browser re-sends Basic auth on its own, so a web
    page a teammate opens could submit those forms to the server behind their back. (It would need
    the server's tailnet address, so it's unlikely, but a forged firmware upload would reach every
    camera.) The simplest fix is a middleware that rejects a non-`/api/` POST whose `Origin` (or
    `Referer`) isn't the server's own address. While there, add security headers:
    `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` or CSP `frame-ancestors 'none'`,
    and HSTS once HTTPS is on.

17. **Repo housekeeping (Settings → General).** Add topics (for example `raspberry-pi`, `esp32`,
    `fastapi`, `computer-vision`, `integrated-pest-management`) so the project can be found, which
    helps if it goes in a portfolio. Turn on "Automatically delete head branches", so merged
    `claude/...` branches don't pile up.

**CodeQL alerts (round 10).** The first scan after PR #60 opened 12 alerts on master; each was
checked and none is a real problem. All 12 were dismissed in the Security tab on Oct 25, each with
the reason below, and none is open now:

| Alerts | Rule | Why it's not a problem |
|---|---|---|
| #14, #15 | weak hashing of sensitive data | SHA-256 of a 192-bit random API key, not a password; a slow hash adds nothing |
| #12, #13 | clear-text logging | the CLI prints a new key once on purpose; only its hash is stored |
| #11 | clear-text storage | the hub must keep its own key; `identity.json` is created mode 0600 |
| #9, #10 | path injection | the upload's uid must match `SAFE_UID`, and the trap id comes from the database |
| #4–#8 | URL redirection | redirects go to `/traps/{id}` after the id was found, or to a `next` that must be a local path |

**Left for a person:** item 13 needs a decision about the license. Items 3 (type checking) and 5 (Alembic) are bigger pieces
of work, each worth its own PR.

**Next:** choose a license (item 13). Type checking (item 3) and Alembic (item 5) are being done in their own sessions.

## Skipped on purpose

- **Reorganizing into `app/api/`, `core/`, `models/`, `schemas/`, `services/`.** The server is one
  package with about a dozen modules (`app.py`, `models.py`, `services.py`, `settings.py`,
  `pipeline/` and others), which already splits it by concern. A big folder move would make
  `git blame` harder to follow and gain little at this size. It's worth doing only if `app.py`
  grows too big; then split the routes into `APIRouter` modules.
- **Docker / docker-compose.** The server runs straight on a Pi 5 under systemd, with rollback in
  `deploy.sh`. On a Pi, Docker adds build time and SD-card wear, and there are no Postgres or Redis
  dependencies to mirror locally. Revisit this if the server moves to a real cloud host.
- **`python-dotenv`.** `settings.py` already loads `.env` itself.
- **Git LFS.** The largest tracked file is about 110 KB (a markdown file in
  `code-review/gemini-raw/`). Photos, datasets and `*.pt` weights are gitignored, so nothing comes
  close to GitHub's limits. Revisit this only if you decide to commit model weights or sample photos.
- **Older beginner advice: `virtualenv venv`, `pip freeze > requirements.txt`, `echo 'venv' > .gitignore`.**
  `uv` already covers the first. A `uv.lock` (item 1) is better than `pip freeze`: `pip freeze`
  lists every installed package, with no record of which ones you asked for, and differs from one
  machine to the next. Note that `echo … > .gitignore` *replaces* the whole file; use `>>` to add to
  it. This repo's `.gitignore` already covers `.venv/`.
- **SSH keys for GitHub.** That's per-person setup, not something the repo holds. If you make a new
  key, use `ssh-keygen -t ed25519`. The tutorial's `IdentitiesOnly` tip in `~/.ssh/config` helps if
  you keep several keys.
- **`git add .`** works here because `.gitignore` covers the data folders. Pre-commit (item 7) is the
  safety net for anything it misses.
- **From Sairyss/backend-best-practices (a Node.js/TypeScript list):**
  - Load and fuzz testing, OpenTelemetry tracing, profiling and benchmarking: the server takes a
    handful of uploads an hour from a few traps, so there's no load to measure. Profile the
    detection pipeline only if a photo starts taking too long.
  - Blue-green deployment: `deploy.sh` waiting for `/healthz` and rolling back covers the same need
    on one machine.
  - Conventional commits: the `Server:` / `Device:` / `ML:` / `Docs:` prefixes already do this job,
    and nothing here is released on a version number.
  - Code generation, BDD/Cucumber, a wiki: overkill for a two-person capstone; `docs/` serves as
    the wiki.
  - Its ESLint/Prettier/TypeScript advice maps to `ruff` and a type checker (items 2 and 3).
- **From DataCamp's Python backend tutorial:**
  - Redis/Memcached caching, load balancing, sharding/replication, Celery, WebSockets: built for
    much more traffic than a few traps. The Pi 5 has one SQLite file and one worker.
  - Django vs Flask vs FastAPI: FastAPI is already the tutorial's pick for ML-backed APIs.
  - Sentry: optional. `journalctl` on the Pi 5 is enough for two people; consider Sentry's free tier
    only if errors start going unnoticed.
  - Penetration testing: out of scope; items 8, 11 and 16 cover the realistic risks.
- **From the dev.to "GitHub repository best practices" article:**
  - Signed commits, linear history and merge queues in branch protection: optional for two people.
    Requiring PRs and passing tests (item 10) is the part that matters.
  - Naming a branching strategy: GitHub Flow (short branches, PR to `master`) is already what
    CLAUDE.md describes.
  - Project boards and milestones: use them if the course wants progress tracking; Issues are
    already on.
- **From the dev.to "GitHub Secrets" article:** environment secrets with required reviewers,
  organization secrets, Azure Key Vault and OIDC only matter once Actions deploys somewhere. If you
  ever move deploys into Actions, store the Tailscale auth key as an *environment* secret with
  `master` as the only allowed branch, and pass it to steps through `env:`, never `echo`.
- **From the dev.to "Securing your code with GitHub" article:** extra scanners (SonarCloud, Trivy,
  TfSec) aren't needed, because CodeQL covers the languages that matter here and there's no
  Terraform or container image. Repository security advisories only matter once someone reports a
  vulnerability through item 14.
