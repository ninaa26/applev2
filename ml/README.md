# ML data and experiments

## Get training photos from AMI (primary external source)

```bash
python3 fetch_ami.py --out data/ami --dry-run              # counts only (~330 MB of metadata, cached)
python3 fetch_ami.py --out data/ami --other-moths 60       # download: our moths + 60 common NE moths
```

Checked Sep 23 2026 (adults, all AMI splits): CM 729, OBLR 1,300, **OFM 72**, lesser appleworm 84,
redbanded leafroller 1,300, 900 "other moth" photos at 60 × 15. A few links (the SCAN museum portal)
refuse automated downloads; the script logs them in `manifest.csv` and moves on. `manifest.csv`
also keeps every photo's source URL, for credits.

These are photos of live or pinned moths, **not** moths on sticky liners. Use them to train only,
never to report accuracy. Accuracy numbers come from our own staged-card photos, split by card.

## Model versions (see the architecture page)

| Version | Detector | Species ID | Where it lives |
|---|---|---|---|
| v0 | baseline OpenCV → flatbug | none → BioCLIP 2 zero-shot | `server/sentinel_server/pipeline/` (`SENTINEL_DETECTOR`, `SENTINEL_CLASSIFIER`) |
| v1 | flatbug | BioCLIP 2 / InsectNet / DINOv2 features + logistic regression | next: train on labelled crops from the review queue + AMI |
| v2 | fine-tuned flatbug or YOLO11 | best of v1 vs fine-tuned EfficientNet-B0 | Colab or a Cornell GPU |
