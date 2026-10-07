# Measuring accuracy

`sentinel-server evaluate` compares what the pipeline counted with what a person counted. It
gives the report's three numbers, each with a pass mark:

| Result | How it's measured | Pass mark | Why |
|---|---|---|---|
| Count accuracy per liner | 1 − \|auto − manual\| / manual, per pest and for all moths | ≥ 0.80 | Suto (2022): no standard metric, but forecasting tolerates ~20% error |
| Count per trap-day | new moths that day, automatic vs manual: mean error, and days within 20% or one moth | report | a liner's total can be right while its days are wrong, and the biofix is made of days |
| Detection | a detection matches a drawn insect when IoMin = overlap / smaller box > 0.5 | report P / R / F1 | Ding & Taylor (2016); fairer than IoU for small insects in loose boxes |
| Detection by size | recall and species accuracy by the drawn insect's long side (under 30, 30–75, 75–150, over 150 px) | report | accuracy swings ~20 points between small and large crops (AMI dataset); an average hides the OFM |
| False moths by cause | every detection counted as a moth that is not one: bycatch, debris, or nothing there | report | Preti et al. (2021): up to 67% false positives in a codling moth trap, from scales, leaves, lure shadow and flies |
| Tracking | insects given more than one track (counted twice), tracks that took in more than one insect | report | most papers only check tracks by eye |
| Photos | share left out (blurred, scale or grid misread) and why; px/mm and the OFM's length in px (need ≥ 50); worst glare; oldest liner | report | ~7% of camera-trap photos were unusable in one study; resolution sets what can be told apart |
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

**`boxes.csv`** (optional, for the detection scores): draw a box around every insect on a few photos,
e.g. in any image viewer that shows pixel coordinates, or with a labelling tool that exports boxes.
Box every insect, also the tiny, blurred, half-hidden and decayed ones: leaving them out makes the
score look better than the count will be. Box debris too (leaf bits, loose scales, the lure) with the
label `debris`: it is not an insect to find, but it tells the report what a false moth was. To score
tracking, box the same liner on two or more days and give each insect a name in `insect` (anything,
as long as it is the same in every photo).

```csv
photo,x1,y1,x2,y2,label,insect
20261007T110000Z_T1.jpg,412,220,470,248,CM,a
20261008T110000Z_T1.jpg,413,221,470,249,CM,a
20261008T110000Z_T1.jpg,150,300,171,322,debris,
```

## What the locked test cards must include

The known failure modes, so the numbers mean something (from Suto 2022, Trapview, Preti et al.):

- **touching insects**: at least a few pairs placed wing to wing, end to end and crossed;
  the detector splits them or counts them by size and sends them to review;
- **look-alikes**: other tortricids, lesser appleworm, redbanded leafroller next to the targets;
- **debris**: leaf bits, twigs, seeds, insect parts, dust;
- **bycatch**: flies, small wasps, beetles (`other_insect`);
- **ageing**: leave some cards in for a week or more, since moths lose scales and change on the glue
  (wing patterns were badly degraded after ~72 h in a fall armyworm study);
- **the smallest target at the worst place**: OFM (6 mm) in the card's corners, where the wide lens
  gives 10–11 px/mm instead of 15;
- **the rim**: an insect within a few mm of the card's edge (the detector ignores the outer 4 mm);
- **spread wings**: a moth stuck with its wings open, which detectors count twice;
- **a full liner**: one card past 60 insects, where counts stop being trustworthy and the liner should
  have been changed.

Any change to the trap's colour, liner, light, camera or its height means new locked cards: results
measured before the change don't carry over.

Keep the locked cards out of training: list them in `ml/data/own/locked_test.txt` (see `ml/README.md`).
