# Insect-ML research: what we did with each finding

Status of every item in "Moth Monitoring Machine Learning (Data, Classification, Evaluation)" (Oct 6 2026)
against this repo, as of Oct 8 2026. Start with what could **not** be done; the full item-by-item list follows.
The imaging, detection and counting notes are in [cv-research-status.md](cv-research-status.md).

Words used: **Done** = changed in code or docs on Oct 6–7 2026 and tested. **Had** = already how the repo
worked. **Tested** = tried on our data, with the result; "kept" or "dropped" says what we did. **Not ours** =
about light traps, other hardware or other pests. **Open n** = see the first two sections.

Every "tested" number is the v1 species head (BioCLIP 2 features + linear head) on other people's liner photos,
on liners no head trained on (`ml/eval_liner_species.py`, 15 px/mm unless said): 162 OFM, 87 other insects,
4 debris from OFM trap-camera liners and 37 CM from phone photos of CM cards. The species is the uploader's
claim and the camera is not ours, so they choose between options; they are not trap accuracy. The v2 rows
(Oct 8 2026) are fine-tuned CNNs on the later, larger held-out set (785 crops, field cards included), next to v1 on the same crops.

## Could not be done here

| # | Item | Why not | What would settle it |
|---|---|---|---|
| 1 | Training and testing on our own trap, across a season, with decayed moths and crowded liners | `ml/data/own/` does not exist: the server holds 6 webcam photos and no reviews. Everything "real" in training is other people's liners | Run the trap, review on the dashboard, `export_server_crops.py`, lock test cards, `train_v1.py --final` |
| 2 | Species checked by someone who knows the moths | Real-liner species now covers all three targets, but from an uploader's claim (OFM liners, CM cards, potato tuber moth) or from Claude reading the field-card photos on Oct 7 2026 (`ml/data/field/species.csv`: 35 OBLR, 20 OFM, 13 CM, 24 left unsure). A head that never saw those cards agrees on 42 of 43 held-out moths, which is two readings, not a check. No look-alike tortricid on glue except one lesser appleworm | A trained eye over `ml/data/field/claude_sheets/` and `species.csv` |
| 3 | The species that really land in each lure's trap here | The papers' look-alike lists are European or for other pests (*Synanthedon myopaeformis*, *Cacoecimorpha pronubana*, *Mythimna*). I have not put names in the fetch scripts from memory; the right list is whatever pass 2 finds on the Geneva field cards, checked with an entomologist | Pass 2, then add the species to `fetch_inat.py` as `lookalike_*` |
| 4 | OFM against lesser appleworm at trap resolution | With lesser appleworm in training, 39 of 132 trap-style lesser appleworm copies are still called OFM (1% at ≥ 0.80; the rest go to review). No real-liner lesser appleworm to check against. The file `OFM and LAW.jpg` among the field cards has 2 moths | Pass 2; if they stay inseparable at 15 px/mm, review every OFM near the biofix (now flagged, see below) |
| 5 | 128 vs 224 px input, and a small custom CNN | The architecture comparison itself was run on Oct 8 2026 (EfficientNet-B0, ConvNeXt-T, MobileNetV3-L on an RTX 3060 Ti): none beats the BioCLIP 2 linear head, and all three fail OFM from a second camera (3–6 of 19 against 18), see `ml/README.md`. Input size and a from-scratch CNN were not tried: with every OFM from one camera they would fail the same way | A second source of OFM first |
| 6 | Intermediate pre-training on a pest dataset (COCO → IP102 → ours) | Detector-side, needs the IP102 download and GPU hours, and with 25 labelled photos the labels are the limit, not the starting weights (rule in `.claude/rules/ml.md`) | After the OFM liners are fully labelled and a YOLO run is scored |
| 7 | Attention module on the detector (CBAM) | Same reason: an architecture change before the data is fixed | Same |
| 8 | Trap-style training photos on the trap camera's own liner | The blank IMX219 liner photos predate the LED move ([cv-research-status.md](cv-research-status.md), item 3) | Recalibrate, photograph a blank liner, re-run `make_trap_style.py`, `build_dataset.py`, `train_v1.py` |
| 9 | Carrying classifier error into the counts and the biofix as a model | Needs the head's error rates on our trap. The dashboard now collects them (spot checks, below) but there are none yet | A few weeks of spot checks, then correct counts by the agreement rate |
| 10 | R² of daily counts, false positives by cause, and whether a spray decision would change | `sentinel-server evaluate` reports count accuracy per liner, mean error per trap-day, false moths by cause and the biofix date; it has never had real truth files. R² is not computed (one trap, few days: mean error says more) | Truth counts from locked cards |
| 11 | Watching for drift after deployment | Nothing deployed. The two signals to watch are built: spot-check agreement per trap, and the share of catches waiting for review | A season; re-score on locked cards after any change of liner, lure, camera or light |
| 12 | Throwing out bad web photos | `clean_dataset.py` lists 220 photos far from the rest of their species and 21 the head would label differently; a person has to look, because good photos on odd backgrounds are in the same list. Dropping all 220 blind changed nothing on real liners (OFM 0.95, CM 0.89 either way) | Look at `ml/data/clean/*.jpg`, copy the junk into `ml/data/exclude.csv` |
| 13 | A debris score | 4 held-out debris crops (2 found; 95% interval 15–85%) and 9 on field cards (0 found) | Debris from our own liners; rejected detections on the dashboard become `debris` through `export_server_crops.py` |
| 14 | Grouping unknown insects to speed up labelling (morphospecies clustering) | Not built. It would help most on the 454 unlabelled boxes of the OFM liners, but the labeller keeps `labels.csv` in memory, so suggestions cannot be written into it while it is open | A `suggested` column the labeller shows; needs the labeller changed |
| 15 | Results by region | One region (NY). The look-alike and bycatch photos are already NY-only | A second site |
| 16 | Storing results as Darwin Core / Camtrap DP | Not built: it is a biodiversity-data standard, and this trap's output is a count and a date for one grower. The database already keeps every detection's class probabilities and model version | An export command, if the data is ever shared |
| 18 | More correctly labelled photos of the targets | Checked Oct 7 2026: iNaturalist has 58 research-grade OFM observations in the world and 130 of lesser appleworm, GBIF 59 and 44 with images; we hold them all. CM and OBLR have ~10,000 each and we use 2,000; capping at 1,000 changed nothing, so more would not either. The USDA stored-product sticky-trap set (1,739 hourly photos of one Indianmeal moth trap) has no per-insect labels in its public files | Our own trap |
| 19 | An OFM check from a second source | Every public OFM-on-liner photo found is in the one trap-camera set; NC State's OFM card photo is 600 × 401 px | Our own trap, or a photo of an OFM liner from the Geneva station |
| 17 | Comparing with Trapview's reported precision (> 90%) | Vendor number on their traps; ours needs items 1 and 10 first | Item 10 |

## Needs your decision

- **Which biofix runs the degree-day clock.** The trap page now shows the biofix from all counted catches, as
  before, and says "Provisional" when it rests on catches the model was unsure of, with the date from
  confirmed catches alone beside it. The clock still starts from the first. Starting it from confirmed
  catches only is safer against a false start and later whenever nobody reviews.
- **Spot-check rate.** One in ten automatic labels now also goes to the review queue
  (`services.AUDIT_EVERY`). More gives a tighter error estimate and more clicking.
- **Switching the classifier on.** The server still runs `SENTINEL_CLASSIFIER=none` and its venv has no
  torch. Nothing here changes what the running server does until that is set.
- **The 220 odd photos** (item 12).

## What worked

| Finding | Status | What we do |
|---|---|---|
| RandAugment + mixed resolution (trap accuracy 51.5% → 71.9%) | Done / Tested, v1 kept | `train_v2.py`: RandAugment and `MixRes` (half the photos shrunk to a 48–160 px crop and enlarged back). v1's features are frozen, so its version is the 5–16 px/mm trap-style set and real-liner crops at two resolutions. Oct 8 2026: EfficientNet-B0, ConvNeXt-T and MobileNetV3-L trained with it match v1 overall on the 785 held-out real-liner crops but find 3–6 of 19 OFM on the held-out field card (v1 18), so v1 stays |
| Black padding of crops at inference | Tested, kept ours | AMI padded to avoid stretching a non-square crop. Ours is already a square cut from the photo with liner around the insect, the same framing as the training crops. Same head, held-out OFM liners: our crop finds 0.94 of OFM and 0.80 of other insects; a tight box padded black 0.82 and 0.64; a tight box stretched to square 0.62 and 0.52, with 11% auto-and-wrong. So AMI's point holds (pad, never stretch) and the context crop is better still for a head trained on context crops |
| Mixing target-domain data into training (5% → +13–15 pts) | Done | `liner_crops.py`: 1,611 real-liner crops, 6% of training, now with 881 real non-target moths (potato tuber moth liners): without them the head called 71 of 97 unseen non-target moths OFM, with them 3. Numbers for the first step: OFM found 0.43 → 0.96, counted automatically as something else 0.19 → 0.00; CM 0.89 → 0.89 (10 px/mm). Cost: other insects found 0.97 → 0.80, the rest mostly called OFM below 0.80 |
| Foundation-model prior (BioCLIP 2) | Had | v1 |
| Distilling BioCLIP 2 into a small net | Not ours | Species ID runs on the server, not the Pi |
| GBIF / iNaturalist transfer learning | Had | 13,564 web photos; alone they find 3% of real OFM, so never alone |
| Regional models + per-species cap (1,000) | Had / Tested, dropped | Look-alikes and bycatch are NY-only. Capping every label at 1,000: OFM 0.94, CM 0.95, others the same, val slightly worse (0.732 vs 0.744). Class weights already balance; no cap |
| Label smoothing, AdamW + cosine warm-up | Done / Tested, v1 kept | `train_v2.py`: smoothing 0.1, one warm-up epoch; same Oct 8 runs |
| Separate moth / non-moth filter | Tested, dropped | A moth / other insect / debris head first, then species among moths: OFM found 0.74 (from 0.95), CM 0.84 (from 0.89), auto-and-wrong 1.7% (from 0.6%). One head does better; "called a moth" is in every table of `eval_liner_species.py` |
| ConvNeXt-B / ViT-B/16 | Tested (ConvNeXt-T), dropped | Oct 8 2026, ConvNeXt-T fine-tuned: 0.87 of held-out real-liner crops right (v1 0.89), 6 of 19 field-card OFM (v1 18), 6.6% wrong at ≥ 0.80 (v1 1.3%). ViT-B/16 not tried: same single-camera OFM problem |
| Small custom CNN with heavy augmentation on tiny data | Open 5 | Their comparison was against large nets trained end to end; a frozen foundation backbone is the other answer to tiny data and is what v1 is |
| Attention module on a lightweight detector | Open 7 | |
| Hierarchical transfer COCO → IP102 → target | Open 6 | |
| Simple open-set scoring (max softmax + temperature) | Done | `train_v1.py` fits a temperature on real-liner val crops (T = 1.65) and saves it in the head; server, playground and scorers divide logits by it. Fitted on web photos it came out 0.9–1.1 and did nothing |
| Expert-curated outlier species; more species beats more images | Had / Open 3 | `other_moth` is NY tortricids across many species plus 60 common NE moths, lesser appleworm and redbanded leafroller, not a generic set |
| Anomaly / OOD filter on detections | Had | The `debris` class, the review and unknown bands, and two-photo confirmation. Not measurable yet (Open 13) |
| Hierarchical output, stop at the confident rank | Done | Below 0.80 a catch is "the model's guess" and waits for review; the biofix says when it depends on such catches. No new label was added: the six classes are fixed across the repo |
| Morphospecies clustering + human review | Open 14 | |
| Active learning loop | Done | Review queue → `export_server_crops.py` → `data/own/` → `train_v1.py` was there for unsure catches. Added: one in ten sure catches is also reviewed, so confident mistakes get corrected and become training data too |

## What didn't work

| Pitfall | Status | How we avoid it |
|---|---|---|
| Training only on GBIF / iNaturalist / museum photos | Done | Trap-style copies (had) and real-liner crops (new). Measured here: web photos alone 3% of real OFM, with trap-style 43%, with real-liner crops 96% |
| Raising input resolution because web accuracy rises | Done / Open 5 | BioCLIP is fixed at 224 and our crops are 110–260 px. Note in `train_v2.py` to compare `--size 128` on real liners. Recall by crop size is now in the report: OFM 13/15 under 80 px, 281/292 at 80–180 px |
| ConvNeXt with no prior and no trap data | Had | v1 has both |
| Large pretrained nets fine-tuned on ~2,000 images | Had / Tested, dropped | v1 trains 4,600 weights on frozen features. v2 fine-tunes on 27,000 photos with heavy augmentation; Oct 8 2026 it did not beat v1: all three CNNs learnt the one trap camera that every training OFM came from (3–6 of 19 OFM from a second camera, v1 18) |
| Forcing a species label on everything | Done | Statuses auto / review / unknown were there; the temperature makes them mean something; the biofix now shows when it rests on unconfirmed catches. Unseen look-alike test below |
| Complex open-set methods | Had | None used |
| Generic outlier data | Had | None used |
| Adding arachnids to the class list | Tested, kept | Without the spider photos: OFM 0.95, CM 0.89, other insects 0.80, identical. Spiders do land on liners, so they stay in `other_insect` |
| Pooling distinct species into one class | Tested, kept pooled | A head on the 15 fine labels, added up to 6 classes: OFM 0.30 (from 0.46), CM 0.64–0.76 (from 0.82), on the earlier head. The pooled classes are what the grower needs and they score better |
| Visually mixed coarse classes ("beetle", "bug", "other") | Tested, kept | Same test. `other_insect` finds 0.80 of real bycatch; it needs to be "not a moth", not a name |
| Non-selective lures with a species classifier | Had | Species-specific pheromone lures, one per trap; the lure mask keeps the lure out of the count |
| Mimics and close relatives | Tested / Open 3, 4 | Lesser appleworm left out of training entirely: 27% of its web photos and 39% of its trap-style copies are called OFM, but 3% reach 0.80; max-softmax separates it from known species at AUROC 0.96 (web), 0.85 (trap-style). So an unseen look-alike mostly lands in review, not in the count |
| Damaged or decayed specimens | Done / Open 1 | The tracker votes on species only in a moth's first 72 h (CV side). The real OFM liners are days old and now train the head. Nothing aged for CM or OBLR |
| Fully automatic counts | Done | Review queue, spot checks, provisional biofix |

## Overlooked considerations

| Item | Status | What we do |
|---|---|---|
| Posture mismatch (pinned, spread reference photos) | Tested, kept | Without the AMI (GBIF, part museum) photos: OFM 0.49 vs 0.46, CM 0.84 vs 0.82, worse on trap-style. No clear gain; kept. The spread and pinned ones are at the top of `clean_dataset.py`'s list |
| Clean citizen-science data | Done / Open 12 | Had: duplicates, AMI copies of iNat photos, images under 100 px, annotated larvae. New: `clean_dataset.py` and `data/exclude.csv`. Asking BioCLIP zero-shot "caterpillar or adult?" was tried and is wrong (its picks were adult moths) |
| Long tail | Had | OFM has 117 web photos; every photo of every observation is fetched, class weights balance, and 632 real-liner OFM crops now outnumber them |
| Species missing from training | Tested / Open 3 | See "mimics" above |
| Cryptic species | Open 4 | None of ours is a true cryptic pair; OFM / lesser appleworm is the hard one |
| Temporal leakage | Had | Splits by observation, card or liner; a liner's other days go with it (`liners.json`); held-out liners are a fixed list (`liner_crops.TEST_GROUPS`) |
| Small test sets | Done / Open 2, 13 | Recall now comes with a 95% interval. Liners are held out rather than added to training because a third of the moths is the only real test there is |
| Label granularity | Had | Pass 1 (moth / other insect / debris) and pass 2 (species) are scored separately; `eval_field_cards.py` folds the head's classes to pass-1 level |
| Report by crop size and by region | Done / Open 15 | Tables per px/mm (15 centre, 10 edge) and by crop side in px |
| Propagate classifier error into the ecology | Open 9 | Spot-check agreement is shown on the trap page |
| Domain shift after deployment | Done / Open 11 | Rule: re-score after any change of trap, lure, liner, camera, light or season |
| Edge vs server | Not ours | |
| Licensing | Done | Ultralytics YOLO is AGPL-3.0, weights included: fine for a course project with public code; a closed product needs their licence or another detector. Photo licences are per row in `dataset.csv` |
| Human review is part of the system | Done | |

## Things not to do

| # | Don't | Status |
|---|---|---|
| 1 | Split by random frame | Had: by observation, card, liner |
| 2 | Validate only on GBIF / iNaturalist / lab images | Done: held-out real liners in `train_v1.py`, `train_v2.py`, `eval_liner_species.py`. Open 1 for our own |
| 3 | Raise input resolution because web accuracy rises | Done / Open 5 |
| 4 | Fine-tune a large model on a few hundred images | Had: frozen backbone |
| 5 | Force a species label on every crop | Done |
| 6 | Use a global species list | Had: NY |
| 7 | Claim species the images can't separate | Open 4 |
| 8 | Pool visually different taxa, or add unrelated groups, without checking | Tested both ways, kept |
| 9 | Start with complex open-set methods | Had |
| 10 | Use generic outlier datasets | Had |
| 11 | Swap architectures before fixing data and augmentation | Done: data first (0.43 → 0.96 from data alone); three architectures compared after, Oct 8 2026, none better than v1 |
| 12 | Skip human verification for first-of-season or high-stakes detections | Done: provisional biofix. Needs your decision on which date runs the clock |
| 13 | Ship AGPL YOLO in a closed product | Done: noted |
| 14 | Treat vendor accuracy claims as validated | Open 17 |

## Pest traps

| Item | Status | What we do |
|---|---|---|
| Closed set: targets, look-alikes, other insect, debris | Had / Open 3 | |
| Train on your own trap images across the season, decayed and crowded included | Open 1 | The route is built and tested: dashboard review → `export_server_crops.py` → `data/own/` |
| Lab-to-field drop is steep | Done | Measured the equivalent: 0.99 on web photos, 0.43 on real liners before, 0.96 after |
| Pre-train on a pest dataset close to yours | Open 6 | |
| Validate with count error, false positives by cause, and the decision | Had / Open 10 | |
| Commercial benchmark | Open 17 | |

## Light traps

Not ours: regional AMI models, morphospecies for tropical data, per-taxon quality across 1,600 species, and
Darwin Core / Camtrap DP (Open 16). The one idea carried over is BioCLIP 2 restricted to a regional list.

## Pipeline checklist

| Step | Status |
|---|---|
| Define classes; merge cryptic species | Had / Open 4 |
| Cleaned web data + own trap crops across a season; cap per species | Done (cleaning list, real-liner crops; cap tested and dropped) / Open 1, 12 |
| Split by night, trap, site; hold out an expert-labelled trap test set | Had / Open 2 |
| Start from a strong prior; compare a small CNN if data is tiny | Had / Tested (three fine-tuned CNNs, v1 kept) / Open 5 (small CNN) |
| ~128 px, RandAugment + mixed resolution, label smoothing | Done in `train_v2.py`, run Oct 8 2026 at 224 px / Open 5 (128 px) |
| Mix in 5–50% trap-domain data; distil for the edge | Done at 4% / Not ours |
| Moth gate and softmax / temperature rejection, thresholds tuned on trap data | Done (temperature and C on real-liner val; gate tested and dropped) |
| Fall back below the confidence threshold | Done (review, provisional biofix) |
| Evaluate on trap data by crop size, region, taxon; macro and micro | Done / Open 15 |
| Route low-confidence and first-of-season detections to a person; feed corrections back | Done |
| Re-validate after any change | Done as a rule / Open 11 |
| Check licences | Done |

## Tested and dropped, so not to be retried without new data

Two-stage moth gate; head on 15 fine labels; capping labels at 1,000; removing spiders; removing AMI photos;
removing the 220 odd web photos; a temperature fitted on web photos; zero-shot life-stage filtering;
black-padded tight crops at inference; fine-tuned CNNs (EfficientNet-B0, ConvNeXt-T, MobileNetV3-L) in place of
v1, until there is OFM on glue from a second camera.
