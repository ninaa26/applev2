# ml/data/: what is in each folder

Everything here is gitignored except this file and `training/held_out/`. The folder names are in
[`ml/paths.py`](../paths.py); the scripts and [ml/README.md](../README.md) are the record of how each folder was made.
The layout dates from Oct 25 2026; `reorganize_data.py` moves a copy in the older flat layout into it.

```
data/
  web_moth_photos/            moths photographed in nature (web), for learning species
    inaturalist/<label>/        iNaturalist, research grade, CC (fetch_inat.py) + manifest.csv
    ami_gbif/<label>/           AMI / GBIF, part museum specimens (fetch_ami.py) + manifest.csv
    cutouts/<label>/            each web insect cut out by flatbug, for pasting (segment_moths.py)

  real_liners/                real insects stuck on real sticky liners
    from_the_web/               other people's liner photos and Roboflow sets; its own README.md says what each
                                subfolder is. species/ holds their insect crops at trap resolution (liner_crops.py)
    cornell_field_cards/        the 11 phone photos of used Trécé cards from the Cornell orchard: inbox/ (photos),
                                labels.csv (boxes, pass-1 labels), species.csv (Claude's species, unchecked),
                                crops/, cutouts/, boxes/, claude_sheets/, eval.md
    our_trap/<label>/<card>/    our own trap's photos, reviewed on the dashboard (export_server_crops.py). None yet
    our_trap_bench_tests/       bench captures from the trap camera (capture_<date>/, each with a README.md)

  trap_style/                 fakes: web insects pasted onto blank liner photos (make_trap_style.py)
    v1_webcam_2026-09/          what models/classifier/bioclip_head/current trained on
      blank_liners/               the backgrounds: 3 photos from the old 640×480 webcam, Sep 24 2026
      photos/<label>/             24,112 fakes
      manifest.csv, preview/
    (v2_<camera>_<date>/          the next set: same layout, blank_liners/ from the IMX219 after recalibration)

  training/                   what training reads and writes
    classifier/                 species ID, on crops of one insect
      dataset.csv                 every photo with its label, source, group and split (build_dataset.py)
      exclude.csv                 photos a person looked at and left out (path, why). Doesn't exist yet
      dropped.csv                 every photo build_dataset.py left out, and why
      bioclip_embeddings/         cached BioCLIP 2 features, keyed by photo path
    detector/                   finding insects, on whole photos with boxes (train_yolo.py)
      yolo_real/                  tiles of the fully labelled field cards and OFM liners
      yolo_blank/                 the same plus blank-liner photos with no boxes
      yolo_synth/                 the same plus web insects pasted onto tiles
    held_out/                   IN GIT: the photos no model trains on (see its README.md). Shared by both models

  review/
    cleaning_suspects/          clean_dataset.py: web photos that may be junk or mislabelled (suspects.csv and a
                                contact sheet per check and label). Nothing is left out until a person copies
                                rows into training/classifier/exclude.csv

  bundle/                     make_bundle.py: a copy to train on another machine (RUN_ON_CUDA.md)
  logs/                       old run logs and shell scripts
  old/                        backups (an earlier dataset.csv, reorganize_data.py's backup and log)
```

Train and test are not separate folders: a photo's split is the `split` column of `dataset.csv` (train, val,
test, locked), and a split keeps every photo of one observation, liner or card on one side. The YOLO folders
have `images/train|val|test` because YOLO needs them; they are copies made by `train_yolo.py`.

Models are in `ml/models/`, also gitignored:

```
models/
  classifier/
    bioclip_head/current/       BioCLIP 2 + linear head (train_v1.py): the one to deploy
    bioclip_head/archive/       older heads, named <date>_<what was different>, kept for comparison
    cnn/<arch>/                 fine-tuned CNNs (train_v2.py)
  detector/
    pretrained/                 downloaded starting weights: flat_bug_M.pt, yolo11s.pt
    yolo/<run>/                 our YOLO11 runs (train_yolo.py)
```

Each model trained since this layout has a `trained_on.json` next to it: the dataset fingerprint, rows by source
and split, trap-style version, held-out lists and git commit. BioCLIP 2 and the ImageNet CNN weights are not here:
they download into `~/.cache/huggingface/` and `~/.cache/torch/` on each machine.
