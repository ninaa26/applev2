# Orchard Sentinel: files for Gemini (Argon)

## Steps

1. Get the live data (only reads from the Pis; takes about a minute):
   `bash code-review/gemini-upload/collect-live.sh`
   It writes `06_live_snapshot.md`. Skim it before you upload.
2. In the Gemini app pick **4 Argon**, start a new chat and attach these files:
   - `01_code_server.txt`: FastAPI server, pipeline, dashboard, tests
   - `02_code_device_and_esp32.txt`: hub gateway, Pi trap code, ESP32 firmware
   - `03_code_ml.txt`: training and labelling scripts, ML rules
   - `04_docs_hardware_fieldtests_ci.txt`: README, CLAUDE.md, docs, hardware, field tests, CI
   - `05_review_findings_so_far.md`: the earlier review (Gemini Flash, checked by Claude)
   - `06_live_snapshot.md`: live status, logs and database counts
3. Also attach `00_ARGON_BRIEF.md` and paste: *"Read 00_ARGON_BRIEF.md first, then do Part A."* Then "Do Part B" and "Do Part C" in the same chat, and Parts D1–D4 each in a new **Deep Research** chat (the brief has the prompts to paste). The table in section 0 of the brief lists every chat. Afterwards, ask follow-ups one area at a time ("now go deep on the ESP32 firmware vs. the
   camera logs").
4. Bring the answer back to Claude to check before changing anything. Argon has been reported to be overconfident
   on code, so every finding needs a file and line that someone can check.

The short prompt that used to be here is replaced by `00_ARGON_BRIEF.md`.
