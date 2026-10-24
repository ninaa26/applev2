# Read-only summary of the server database. Run with the server's .venv python from SERVER_DIR.
import sqlite3, json, sys
db = sqlite3.connect("file:data/sentinel.db?mode=ro", uri=True)
db.row_factory = sqlite3.Row
def q(title, sql):
    print(f"\n### {title}\n")
    try:
        rows = db.execute(sql).fetchall()
    except Exception as e:
        print(f"(query failed: {e})"); return
    if not rows: print("(none)"); return
    cols = rows[0].keys()
    print("| " + " | ".join(cols) + " |"); print("|" + "---|" * len(cols))
    for r in rows: print("| " + " | ".join(str(r[c])[:120].replace("|", "/").replace("\n", " ") for c in cols) + " |")
print("\n### Row counts\n")
for t in [r[0] for r in db.execute("select name from sqlite_master where type='table'")]:
    print(f"- {t}: {db.execute(f'select count(*) from \"{t}\"').fetchone()[0]} rows")
cols = [r[1] for r in db.execute("pragma table_info(traps)")]
safe = [c for c in cols if not any(k in c for k in ("key", "hash", "token", "secret", "password"))]
q("Traps (secret columns left out)", f"select {', '.join(safe)} from traps")
q("Cards (liners)", "select id, trap_id, installed_at, removed_at, note from cards order by id")
q("Photos by trap and status", "select trap_id, status, count(*) n, min(captured_at) first, max(captured_at) last from captures group by trap_id, status")
q("Photos per day, last 14 days", "select date(captured_at) day, trap_id, count(*) n, sum(status='processed') ok, sum(status='failed') failed from captures where captured_at > datetime('now','-14 days') group by day, trap_id order by day")
q("Why photos failed (top 20)", "select substr(error,1,110) error, count(*) n from captures where status='failed' group by 1 order by n desc limit 20")
q("Last 25 photos", "select id, trap_id, card_id, captured_at, received_at, status, model_version, substr(error,1,80) error, substr(meta,1,300) meta from captures order by id desc limit 25")
q("Insects (tracks) by status and species", "select status, species, review_status, count(*) n, round(avg(species_conf),2) conf, sum(n_insects) insects from tracks group by 1,2,3 order by n desc")
q("Reviewed labels", "select reviewed_label, count(*) n from tracks where reviewed_label is not null group by 1")
q("Events, last 60", "select at, trap_id, kind, substr(payload,1,160) payload from events order by at desc limit 60")
q("Event kinds", "select kind, count(*) n, max(at) last from events group by kind order by n desc")
q("Weather days", "select source, count(*) days, min(day) first, max(day) last from weather_days group by source")
