# Measuring accuracy

`sentinel-server evaluate` compares what the pipeline counted with what a person counted. It
gives the report's three numbers, each with a pass mark:

| Result | How it's measured | Pass mark | Why |
|---|---|---|---|
| Count accuracy per liner | 1 − \|auto − manual\| / manual, per pest and for all moths | ≥ 0.80 | Suto (2022): no standard metric, but forecasting tolerates ~20% error |
| Detection | a detection matches a drawn insect when IoMin = overlap / smaller box > 0.5 | report P / R / F1 | Ding & Taylor (2016); fairer than IoU for small insects in loose boxes |
| Biofix | NEWA sustained-catch date from the manual count vs from the automatic count | within 1 day | the date growers actually act on |

It also reports what two-photo confirmation removes: detections seen in one photo and never
again, and what the count would be without confirmation (Preti et al.'s prototype over-counted
1.5–3× without it).

```bash
cd server
.venv/bin/sentinel-server evaluate                                   # confirmation stats, every liner
.venv/bin/sentinel-server evaluate --counts truth/counts.csv --boxes truth/boxes.csv --out eval.md
```

## Making the truth files

**`counts.csv`**: count each liner by hand (from the liner itself, not the photos), writing down
the day each insect first appeared. `card` is the liner's number on the dashboard: the trap page shows it as
"liner #3 installed …" (a new number each time the liner is changed).

```csv
card,date,label,count
3,2026-10-06,CM,2
3,2026-10-07,CM,1
3,2026-10-07,other_moth,1
```

Labels: `CM`, `OFM`, `OBLR`, `other_moth`, `other_insect`, `debris`. Days with nothing new need no row.

**`boxes.csv`** (optional, for the detection score): draw a box around every insect on a few photos,
e.g. in any image viewer that shows pixel coordinates, or with a labelling tool that exports boxes.

```csv
photo,x1,y1,x2,y2,label
20261007T110000Z_T1.jpg,412,220,470,248,CM
```

## What the locked test cards must include

The known failure modes, so the numbers mean something (from Suto 2022, Trapview, Preti et al.):

- **touching insects**: at least a few pairs placed wing to wing, end to end and crossed;
  the detector splits them or counts them by size and sends them to review;
- **look-alikes**: other tortricids, lesser appleworm, redbanded leafroller next to the targets;
- **debris**: leaf bits, twigs, seeds, insect parts, dust;
- **bycatch**: flies, small wasps, beetles (`other_insect`);
- **ageing**: leave some cards in for a week or more, since moths lose scales and change on the glue.

Keep the locked cards out of training: list them in `ml/data/own/locked_test.txt` (see `ml/README.md`).
