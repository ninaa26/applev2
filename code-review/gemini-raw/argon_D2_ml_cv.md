Machine Learning and Computer Vision Architecture for Automated Sticky-Trap Lepidopteran Monitoring on Edge Hardware

Executive Summary and System Bottleneck Analysis

The Orchard Sentinel system is designed to automate integrated pest management (IPM) in commercial apple orchards by photographing the $174 \times 198\text{ mm}$ sticky liner inside an Alpha Scents red corrugated-plastic delta trap using a battery-powered Freenove ESP32-S3-WROOM CAM node and processing uploads on a GPU-free Raspberry Pi 5 server (uploaded:00_ARGON_BRIEF.md). The system monitors three primary tortricid pests—codling moth (CM, Cydia pomonella), oriental fruit moth (OFM, Grapholita molesta), and obliquebanded leafroller (OBLR, Choristoneura rosaceana)—alongside non-target look-alikes (other_moth, other_insect, debris), with the primary agronomic objective of establishing the first sustained catch (biofix) date to within $\pm 1\text{ day}$ and tracking weekly catch thresholds (uploaded:00_ARGON_BRIEF.md, https://extension.unh.edu/resource/fruit-ipm-reports).

An end-to-end audit of the existing Orchard Sentinel computer vision and machine learning architecture against peer-reviewed literature and commercial automated trap pipelines indicates that the system's primary failure modes originate not from its foundation classification backbone (BioCLIP), but from upstream optical, geometric, and domain-shift vulnerabilities that corrupt downstream inference (uploaded:00_ARGON_BRIEF.md, https://arxiv.org/html/2609.30278v1). First, the current narrow-angle OV3660 sensor ($3\text{ MP}$, $\sim 66^\circ$ field of view) mounted at the $110\text{ mm}$ internal apex of the delta trap images only $\sim 115 \times 85\text{ mm}$ ($9,775\text{ mm}^2$), leaving 71.6% of the $174 \times 198\text{ mm}$ ($34,452\text{ mm}^2$) sticky card unmonitored (uploaded:00_ARGON_BRIEF.md). During low-density spring emergence, blinding the detector to over two-thirds of the capture surface introduces multi-day delays in detecting the first sustained flight (https://open-research-europe.ec.europa.eu/articles/6-421). Second, in server/sentinel_server/pipeline/detect.py, the classical OpenCV grid detector misreads 5 out of 10 insect-laden cards as $32–63\text{ px/mm}$ instead of the true $15.3\text{ px/mm}$, while the scale validation logic locks in initial readings (uploaded:00_ARGON_BRIEF.md). Because calibrated morphological length ($4.5–7.0\text{ mm}$ for Grapholita spp. vs. $7.6–12.0\text{ mm}$ for C. pomonella and $9.0–12.0\text{ mm}$ for C. rosaceana) is the most reliable taxonomic discriminator when sticky glue obscures wing scales (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf), a $2\times–4\times$ scale error invalidates size-based filtering and distorts crop geometry.

Third, unpolarized single-LED illumination saturates $10–13\%$ of the glossy polybutene liner (uploaded:00_ARGON_BRIEF.md), creating high-contrast specular blobs that trigger false detections and mask the metallic coppery-bronze apical patch that separates CM from OFM (https://bettertermite.com/pests/moths/codling-moths/, https://fjwoptical.com/blogs/blog/lighting-the-role-of-polarized-lighting-in-reducing-glare-and-reflections). Fourth, because all OFM training crops in the project originate from a single physical trap (uploaded:00_ARGON_BRIEF.md), unregularized classification heads learn background glue tint, red-roof color cast, and lighting gradients rather than insect morphology—a phenomenon proven in multi-region sticky-trap benchmarks (https://arxiv.org/html/2609.30278v1) to cause accuracy drops of $16.2–27.0\text{ percentage points}$ when transferred across traps. Finally, in server/sentinel_server/pipeline/phen[span_2](start_span)[span_2](end_span)ology.py, a single unreviewed false positive during early spring can prematurely trigger the NEWA sustained-catch biofix, shifting degree-day accumulation (DD50 for CM, DD45 for OFM, DD43 for OBLR, https://newa.cornell.edu/crop-and-pest-management) and misaligning larvicidal spray windows (uploaded:00_ARGON_BRIEF.md).

1. Insect Detection on Sticky Liners: Classical vs. Deep Learning Paradigms

Classical OpenCV Detection (Thresholding, Blob Detection, and Grid Removal)

Measured Results: Classical sticky-trap pipelines rely on color-space thresholding, morphological filtering, connected-component analysis, and frequency or intensity-based grid removal. In microscopy and gridded chamber imaging (https://pmc.ncbi.nlm.nih.gov/articles/PMC4652928/), automatic grid removal isolates pixel intensity bands contributed exclusively by printed grid lines (such as grayscale values $130–160$) before segmenting targets. Similarly, shape-based connected-component filtering (https://scienmag.com/slideprep-removes-chamber-grids-and-reconstructs-whole-slide-microscopy-images/) separates compact biological targets from elongated grid lines, while grayscale structural morphology (https://www.technetexperts.com/extract-line-graph-data-python/) erodes and reconstructs rectilinear lines. On orchard delta traps (uploaded:00_ARGON_BRIEF.md), however, the classical OpenCV grid finder in detect.py fails on $50\%$ of cards containing insects, reporting $32–63\text{ px/mm}$ instead of $15.3\text{ px/mm}$. Furthermore, automated image quality evaluations on field traps (https://www.mdpi.com/2071-1050/14/15/9729) demonstrate that shadows and reflections limit classical segmentation and reflection-assessment accuracy to $80\%$ on delta traps compared to $96\%$ on cylindrical traps, even when achieving a $97\%$ Jaccard index on clean laboratory cards.

Engineering Analysis and Opinion: Classical thresholding and morphological grid removal are structurally brittle on field-deployed pheromone liners (Confidence: Sure). When moths land across printed $25\text{ mm}$ grid lines, their dark wings bridge adjacent grid segments, while dark wing striae and specular LED glare introduce high-frequency spatial edges at $2\times$ to $4\times$ the true grid harmonic ($30.6\text{ px/mm}$ to $61.2\text{ px/mm}$), causing Hough or autocorrelation peak finders to lock onto false harmonics. Moreover, subtracting grid lines via morphological opening leaves behind fragmented insect contours whenever a moth's legs or antennae align with a grid line, while glue yellowing, pollen accumulation, and shadow gradients from the triangular roof panels continuously shift background thresholds over a 28-day liner cycle (https://www.researchgate.net/figure/A-Three-consecutive-photographs-taken-by-the-IR-camera-the-fi-rst-two-were-taken-before_fig3_355318381, https://www.mdpi.com/2071-1050/14/15/9729).

YOLO-Family vs. DETR vs. SAM-Based Segmentation

Measured Results: Deep learning object detectors eliminate the need for explicit grid-line removal by learning invariance to rectilinear background patterns. Controlled benchmarks on pheromone trap imagery (https://pmc.ncbi.nlm.nih.gov/articles/PMC11922902/) directly compared one-stage YOLO detectors against two-stage CNNs and vision transformers. End-to-End Object Detection with Transformers (DETR) achieved $81.1\%$ recall, $91.3\%$ precision, and $93.8\%\text{ mAP@0.5}$ (https://pmc.ncbi.nlm.nih.gov/articles/PMC11922902/). While the BIOSCAN-5M pipeline (https://arxiv.org/html/2406.12723v1) successfully fine-tuned DETR on $2,837$ single-specimen laboratory microscope images ($2,000$ base images plus $837$ hard examples) for bounding-box cropping, standard DETR exhibits substantially lower recall ($81.1\%$) on multi-target trap scenes than modern YOLO architectures. Recent specialized transformer variants such as PestFG-RTDETR (https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2026.1940983/full) and RF-DETR (https://www.robolabs.ai/ar/resources/blog/benchmarking-reality-check-cv-model-deployment) incorporate frequency-spatial fusion to recover small-object recall, but require GPU acceleration ($12.1\text{ ms}$ at $28\text{ W}$ on Jetson Orin for RF-DETR-S).

Among two-stage convolutional detectors, the open-source Sticky Pi system (https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3001689, https://www.biorxiv.org/content/10.1101/2021.08.11.455750v1.full) trained a Mask R-CNN "Universal Insect Detector" on sticky cards, achieving $69.6\%$ overall recall and $90.5\%$ precision, which rose to $79.3\%$ recall when excluding the smallest $25\%$ of objects ($<1,000\text{ px}^2$ area). In pheromone traps (https://pmc.ncbi.nlm.nih.gov/articles/PMC11922902/), Cascade R-CNN reached $90.7\%$ recall, $91.7\%$ precision, and $94.4\%\text{ mAP@0.5}$. By contrast, one-stage YOLO-family architectures (YOLOv8, YOLOv9, YOLOv11, YOLO26) dominated both accuracy and efficiency: on the same pheromone trap benchmark (https://pmc.ncbi.nlm.nih.gov/articles/PMC11922902/), YOLOv8m achieved $92.9\%$ recall, $93.6\%$ precision, and $94.2\%\text{ mAP@0.5}$, while YOLOv9-TrapPest reached $96.6\%$ recall, $97.5\%$ precision, and $98.3\%\text{ mAP@0.5}$. On edge camera-trap benchmarks (https://arxiv.org/htm[span_32](start_span)[span_32](end_span)l/2509.20318v2, https://www.mdpi.com/2079-9292/15/5/1026), nano architectures—specifically YOLOv11n ($2.58\text{M}$ parameters, $6.31\text{ GFLOPs}$) and YOLOv8n ($3.01\text{M}$ parameters, $8.09\text{ GFLOPs}$)—achieved $0.9920$ and $0.9918\text{ AP@0.5}$ on Roboflow subsets and $0.7395$ and $0.7199\text{ AP@0.5}$ on challenging wild camera traps, outperforming YOLOv10s ($7.22\text{M}$ parameters, $21.41\text{ GFLOPs}$, $0.7334\text{ AP@0.5}$) at less than one-third the compute cost. Meanwhile, Segment Anything (SAM) has been deployed in sticky-card workflows such as PeMaToEuroPep ("Flat Bug", https://zenodo.org/records/13930055) strictly as an offline, semi-automated annotation tool to generate polygon instance masks across $284$ sticky-card images, whereas lightweight edge segmentation pipelines (https://arxiv.org/html/2404.17488v1) rely on compact U-Net architectures rather than heavy SAM backbones.

Detection Paradigm	Representative Architecture	Measured Trap Precision / Recall / mAP	Compute Profile (GFLOPs / Params)	Suitability for Pi 5 CPU Sticky-Trap Inference	Primary Source URL
Classical OpenCV	Thresholding + Hough/FFT Grid Removal	Fails scale check on 50\% of insect cards (32–63\text{ px/mm})	<0.1\text{ GFLOPs} / 0\text{ Params}	Poor: Brittle to touching moths, glare, and grid occlusion	uploaded:00_ARGON_BRIEF.md
Two-Stage Instance Seg.	Mask R-CNN (Sticky Pi Universal Detector)	90.5\%\text{ Prec.} / 69.6\%\text{ Rec.} (79.3\% for >1000\text{ px}^2)	>100\text{ GFLOPs} / \sim 44\text{M}	Poor: Heavy latency (>2\text{ s/img} on CPU)	https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3001689
Two-Stage Cascade CNN	Cascade R-CNN	91.7\%\text{ Prec.} / 90.7\%\text{ Rec.} / 94.4\%\text{ mAP50}	>120\text{ GFLOPs} / \sim 69\text{M}	Poor: Requires GPU for practical throughput	https://pmc.ncbi.nlm.nih.gov/articles/PMC11922902/
Vision Transformer (DETR)	Vanilla DETR / PestFG-RTDETR	91.3\%\text{ Prec.} / 81.1\%\text{ Re[span_33](start_span)[span_33](end_span)c.} / 93.8\%\text{ mAP50}	50–180\text{ GFLOPs} / 30–42\text{M}	Poor: Low small-object recall in vanilla DETR; high CPU latency	https://pmc.ncbi.nlm.nih.gov/articles/PMC11922902/
Foundation Segmentation	SAM (Segment Anything)	Used for semi-automated ground-truth polygon labeling	>300\text{ GFLOPs} / 90–636\text{M}	Offline Only: Ideal for annotation (Zenodo 13930055), not Pi 5 inference	https://zenodo.org/records/13930055
One-Stage Nano CNN	YOLOv11n / YOLOv8n / YOLO26n	92.3–98.9\%\text{ Prec.} / 57.7–98.5\%\text{ Rec.} / 74–99\%\text{ AP50}	6.3–8.7\text{ GFLOPs} / 2.6–3.2\text{M}	Optimal: 83.7–95.2\text{ ms} on Pi 5 CPU via OpenVINO/NCNN; ignores grid lines	https://arxiv.org/html/2509.20318v2

Engineering Analysis and Opinion: Replacing the OpenCV blob detector in detect.py with a single-class (insect) or 2-class (moth, other_insect_or_debris) YOLOv8n or YOLOv11n detector is the highest-leverage algorithmic upgrade available (Confidence: Sure). A class-agnostic YOLOv8n/YOLOv11n localization network requires only $150–300$ annotated sticky-card images to converge, completely ignores the printed $25\text{ mm}$ grid without needing destructive grid-removal filters, and executes in under $100\text{ ms}$ on a Raspberry Pi 5 CPU (https://www.researchgate.net/publication/393313265_Real-time_small_object_detection_with_YOLOv8n8s_and_YOLOv11n11s_models_in_complex_natural_landscapes, https://zenodo.org/records/13930055). SAM should be used strictly on a development workstation to rapidly generate polygon masks for training data curation (https://zenodo.org/records/13930055).

Small-Object Tricks (SAHI, ASAHI-AR, and High-Resolution Tiling)

Measured Results: Slicing-Aided Hyper Inference (SAHI) divides high-resolution trap images into overlapping patches, runs detection on each patch, and merges predictions alongside an optional full-image inference pass using Non-Maximum Suppression (NMS) (https://pmc.ncbi.nlm.nih.gov/articles/PMC11624506/, https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2024.1484587/full). In field trials of YOLOv8 + SAHI on rice sticky traps (https://github.com/Gvtone/insect-trap-webpage), SAHI achieved $72.01\%$ precision, $62.53\%$ recall, and $65.72\%$ F1-score, outperforming five non-sliced YOLO variants. Similarly, YOLOv11n with slice inference (https://www.sciopen.com/article/10.11975/j.issn.1002-6819.202506243) and YOLO26-USW (https://www.mdpi.com/2073-4395/16/20/2043) demonstrated substantial recall gains for tiny ($1–3\text{ mm}$) greenhouse and light-trap pests.

However, a critical 2026 study by Nekka et al. (https://zenodo.org/records/22922085, "Counting Is Not Detecting: Resolution, Cadence and Decision Error in Automated Sticky-Trap Insect Monitoring") and a controlled 5-fold cross-validation benchmark on INSECT-SOYBEAN-DET-1C (https://www.preprints.org/manuscript/202609.1035/v1) exposed a severe flaw in standard SAHI when applied to insect counting. While standard SAHI boosted YOLOv8n recall to $0.674 \pm 0.037$ (from a baseline $\text{mAP@[.5:.95]}$ of $0.128 \pm 0.009$) and Faster R-CNN recall to $0.895 \pm 0.015$ (from a baseline $\text{mAP@[.5:.95]}$ of $0.112 \pm 0.012$), standard SAHI degraded Faster R-CNN counting RMSE by $+201\%$, inflating error from $3.725 \pm 0.357$ to $11.209 \pm 0.602$ insects per image (https://www.preprints.org/manuscript/202609.1035/v1). When an insect straddles the boundary between overlapping tiles, truncated bounding boxes in adjacent slices exhibit low Intersection-over-Union (IoU) with one another, surviving standard NMS and generating duplicate counts. Adaptive SAHI with Aspect-Ratio adjustment (ASAHI-AR, using a $4 \times 3$ adaptive grid on $4032 \times 2268$ images) paired with IoA-SoftNMS (Intersection-over-Area SoftNMS) eliminated redundant slices and achieved the highest YOLOv8n F1-score ($0.627 \pm 0.020$) and Faster R-CNN $\text{mAP@[.5:.95]}$ ($0.315 \pm 0.007$) without inflating count MAE or RMSE (https://www.preprints.org/manuscript/202609.1035/v1).

Detector & Slicing Strategy	Detection \text{mAP@[.5:.95]}	Detection Recall	Detection F1-Score	Counting Error (RMSE)	Key Trade-Off Observed	Primary Source URL
YOLOv8n Baseline (No Slicing)	0.128 \pm 0.009	Baseline	Baseline	Statistically stable group	Misses tiny targets in 4032 \times 2268 scenes	https://www.preprints.org/manuscript/202609.1035/v1
YOLOv8n + Standard SAHI	Intermediate gain	0.674 \pm 0.037	Intermediate	Statistically stable group	High tile count; boundary splits require IoA suppression	https://www.preprints.org/manuscript/202609.1035/v1
YOLOv8n + ASAHI-AR	Best group	Best group	0.627 \pm 0.020	Statistically comparable to baseline	Optimal aspect-ratio-aware 4 \times 3 grid balance	https://www.preprints.org/manuscript/202609.1035/v1
Faster R-CNN Baseline (No Slicing)	0.112 \pm 0.012	Baseline	Baseline	3.725 \pm 0.357	Low recall on small targets but low false-duplicate rate	https://www.preprints.org/manuscript/202609.1035/v1
Faster R-CNN + Standard SAHI	Intermediate gain	0.895 \pm 0.015	Degraded by FPs	11.209 \pm 0.602 (+201\%)	Severe boundary double-counting inflates RMSE	https://www.preprints.org/manuscript/202609.1035/v1
Faster R-CNN + ASAHI-AR	0.315 \pm 0.007	High	High	Controlled via reduced tile redundancy	Retains recall gains while curbing duplicate boxes	https://www.preprints.org/manuscript/202609.1035/v1

Engineering Analysis and Opinion: For the Orchard Sentinel pipeline, 12-tile SAHI should NOT be used (Confidence: Sure). SAHI was designed for micro-pests ($1–2\text{ mm}$ whiteflies and thrips occupying $15 \times 15\text{ px}$ in $12\text{ MP}$ images, https://www.sciopen.com/article/10.11975/j.issn.1002-6819.202506243, https://wildlabs.net/en/discussion/detecting-thrips-and-larger-insects-together?language_content_entity=en). At Orchard Sentinel's scale ($14.8–18.0\text{ px/mm}$), target tortricid moths (OFM, CM, OBLR) measure $4.5–12.0\text{ mm}$ in body length (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf, https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/obliquebanded-leafroller-choristoneura-rosaceana-fruit-ipm-fact-sheet), spanning $67\text{ to }215\text{ pixels}$ in length. Slicing a $2048 \times 1536$ or $2592 \times 1944$ card into small $640 \times 640$ tiles cuts directly across $100\text{ px}$-long moths, inducing the exact boundary double-counting documented in Preprints 202609.1035 (https://www.preprints.org/manuscript/202609.1035/v1) while multiplying Raspberry Pi 5 CPU inference latency by $6\times–12\times$. Instead, running YOLOv8n or YOLOv11n on the full rectified card at imgsz=960 (or at most a $2 \times 1$ stereo-overlap split merged via IoA-SoftNMS where $\text{IoA} = \frac{\text{Area}(A \cap B)}{\min(\text{Area}(A), \text{Area}(B))} > 0.65$) captures every moth intact in a single forward pass.

Touching and Overlapping Insects

Measured Results: When pheromone plumes draw heavy male flights, moths frequently land in contact or overlap on the glue (https://www.mdpi.com/2073-4395/15/9/2022, https://www.researchgate.net/publication/349640552_Field_detection_of_tiny_pests_from_sticky_trap_images_using_deep_learning_in_agricultural_greenhouse). Classical pipelines (https://arxiv.org/html/1809.06663v1) apply distance-transform watershed segmentation inside merged binary contours, which yields two outcomes: either the watershed basins successfully cleave touching insects into distinct regions, or heavily fused bodies remain a single refined contour. Deep learning approaches address pest adhesion and aggregation (https://www.mdpi.com/2073-4395/15/9/2022) by replacing standard CIoU box regression loss with inner-MPDIoU (https://www.mdpi.com/2073-4395/14/5/1034, reaching $98.17\%\text{ mAP@0.5}$ and outperforming Faster R-CNN, SSD, YOLOv5, YOLOv7, and baseline YOLOv8 by $2.71–17.04\%$) or WIoU v3 (https://www.mdpi.com/2073-4395/16/20/2043), which penalize center-point shifts and preserve adjacent bounding boxes during NMS.

Engineering Analysis and Opinion: In a time-lapse trap capturing 6 photos per day (uploaded:00_ARGON_BRIEF.md), temporal arrival disambiguation is far more reliable than single-frame watershed splitting (Confidence: Sure). Two moths almost never land on the exact same coordinates within the same 4-hour interval; rather, Moth A lands in frame $t_1$, and Moth B lands adjacent to or partially overlapping Moth A in frame $t_k$. By subtracting the known spatial mask of Track A (established at $t_1$) from the merged foreground contour at $t_k$—or by using YOLOv8n/YOLOv11n trained with SoftNMS and inner-MPDIoU where existing track centroids act as spatial priors—the pipeline cleanly isolates Moth B's bounding box and crops only the newly added region for BioCLIP classification (https://www.mdpi.com/2073-4395/14/5/1034, https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3001689).

2. Species Identification: Morphology, Resolution, Foundation Models, and Domain Shift

Morphological Separation of CM, OFM, OBLR, and Look-Alikes on Sticky Glue

Measured Results: Accurate visual separation of the three target tortricids and common orchard bycatch requires combining calibrated physical dimensions ($\text{mm}$) with forewing scale patterns. For Codling Moth (CM, Cydia pomonella, Subfamily Olethreutinae), laboratory morphometrics (https://www.researchgate.net/figure/The-reared-codling-moth-Cydia-pomonella-in-the-laboratory-a-Mature-larva-left-the_fig2_334636702) measure adult male wingspan at $17.05 \pm 0.50\text{ mm}$ (body length $7.60 \pm 0.12\text{ mm}$, width $1.82 \pm 0.04\text{ mm}$, weight $17.38 \pm 0.65\text{ mg}$) and female wingspan at $19.80 \pm 0.50\text{ mm}$ (body length $8.89 \pm 0.13\text{ mm}$, width $2.32 \pm 0.05\text{ mm}$, weight $27.85 \pm 0.79\text{ mg}$), with field identification guides (https://bettertermite.com/pests/moths/codling-moths/) reporting resting lengths of $9–12\text{ mm}$ ($\sim 3/8\text{ to }1/2\text{ inch}$) and wingspans of $\sim 19\text{ mm}$ ($3/4\text{ inch}$). At rest, CM adults fold their wings like a low tent over the body (https://bettertermite.com/pests/moths/codling-moths/). Forewings display alternating wavy gray and white bands ("wood-grain" striae) culminating in the definitive diagnostic mark: a shiny, coppery-brown to metallic bronze apical patch (ocellus) near the distal tip of each forewing (https://bettertermite.com/pests/moths/codling-moths/, https://www.researchgate.net/figure/The-reared-codling-moth-Cydia-pomonella-in-the-laboratory-a-Mature-larva-left-the_fig2_334636702).

By contrast, Oriental Fruit Moth (OFM, Grapholita molesta, Subfamily Olethreutinae) is significantly smaller, with wingspans of $11–15\text{ mm}$ ($1/2\text{ to }3/5\text{ inch}$ in Grapholita datasheets, https://caps.ceris.purdue.edu/wp-content/uploads/2025/07/Grapholita-funebrana-CAPS-Datasheet-2024.pdf) and resting body lengths on sticky traps of $4.5–7.0\text{ mm}$ (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf). Its forewings are uniform slate-gray to dark gray-brown with faint whitish costal markings, completely lacking the metallic coppery-bronze wing-tip patch (https://bettertermite.com/pests/moths/codling-moths/). Obliquebanded Leafroller (OBLR, Choristoneura rosaceana, Subfamily Tortricinae) is considerably larger, with wingspans ranging from $17\text{ to }30\text{ mm}$ (https://www.cabidigitallibrary.org/doi/full/10.1079/cabicompendium.13080, https://www.oregonblueberry.com/korea/identifiedpest.pdf); Cornell IPM specifies a $20–27\text{ mm}$ wingspan and $9–12\text{ mm}$ resting body length (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/obliquebanded-leafroller-choristoneura-rosaceana-fruit-ipm-fact-sheet), while the UVM Tortricidae guide lists $20\text{ mm}$ for males and $25\text{ mm}$ for females (https://www.uvm.edu/femc/attachments/project/999/reports/Torticidae.pdf), with male forewing lengths of $7.5–11\text{ mm}$ (https://www.marylandbiodiversity.com/species/6102, https://en.wikipedia.org/wiki/Choristoneura_rosaceana). At rest, OBLR wings form a broad bell-shaped outline and are tan, orange-brown, or reddish-brown crossed by three dark brown oblique bands (basal patch, median oblique band, and preapical costal band) (https://www.uvm.edu/femc/attachments/project/999/reports/Torticidae.pdf).

Common orchard look-alikes (other_moth) include the Lesser Appleworm (LAW, Grapholita prunivora), which has a wingspan of $9.5–11.0\text{ mm}$ and a forewing length of $4.0–5.0\text{ mm}$ (https://www.cabidigitallibrary.org/doi/full/10.1079/cabicompendium.29907, https://storymaps.arcgis.com/stories/d1020dd771a74bb99d19695ea65516d5) with dark brown-black forewings bearing orange spots and three pale-blue transverse lines, as well as non-target leafrollers and olethreutines such as Acleris chalybeana ($20–25\text{ mm}$ wingspan, light gray with costal spot), Archips semiferana and Archips spp. ($20–28\text{ mm}$ wingspan, orange-brown with costal spots), Catastega/Epinotia ($12–17\text{ mm}$ wingspan, gray with V-shaped bands) (https://www.uvm.edu/femc/attachments/project/999/reports/Torticidae.pdf), and Gymnandrosoma or Ecdytolopha ($8–12\text{ mm}$ length) (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf). Crucially, USDA-APHIS tortricid sticky-trap screening protocols (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf) document that moths coated in sticky-trap glue appear solid black or uniform dark brown, erasing delicate wing-scale patterns and leaving calibrated body length ($\text{mm}$)—such as the $2–4\text{ mm}$ size gap separating $8–12\text{ mm}$ larger tortricids from $4.5–7.0\text{ mm}$ Grapholita spp.—and resting silhouette outline as the primary visual discriminators.

Species / Class	Resting Body Length (mm)	Wingspan (mm)	Resting Silhouette	Diagnostic Forewing Pattern (Clean)	Appearance When Saturated in Glue	Primary Source URL
OFM (Grapholita molesta)	4.5–7.0\text{ mm}	11.0–15.0\text{ mm}	Narrow sub-triangular tent	Plain slate-gray/brown; faint whitish costal strigulae; no copper tip	Small (4.5–7\text{ mm}) dark charcoal/black oval; strigulae often lost	https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf
LAW (Grapholita prunivora)	4.0–5.5\text{ mm}	9.5–11.0\text{ mm}	Narrow sub-triangular tent	Dark brown/black with orange spots & 3 pale-blue transverse lines	Nearly indistinguishable from OFM if glue wicks into orange/blue scales	https://www.cabidigitallibrary.org/doi/full/10.1079/cabicompendium.29907
CM (Cydia pomonella)	7.6–[span_120](start_span)[span_120](end_span)[span_122](start_span)[span_122](end_span)12.0\text{ mm} (\sigma\text{ }7.6, \circ\text{ }8.9)	17.0–20.0\text{ mm} (\sigma\text{ }17.1, \circ\text{ }19.8)	Elongated low tent	Wavy gray-white wood-grain striae; metallic coppery-bronze apical patch	2–4\text{ mm} longer than OFM; bronze patch retains specular sheen longer than gray scales	https://www.researchgate.net/figure/The-reared-codling-moth-Cydia-pomonella-in-the-laboratory-a-Mature-larva-left-the_fig2_334636702
OBLR (Choristoneura rosaceana)	9.0–12.0\text{ mm} (FW 7.5–11)	17.0–30.0\text{ mm} (typ. 20–27)	Broad, flared bell-shape	Tan/reddish-brown with 3 dark oblique bands across forewing	Large bell silhouette (9–12\text{ mm}); warm brown hue and broad shoulders persist	https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/obliquebanded-leafroller-choristoneura-rosaceana-fruit-ipm-fact-sheet

Spatial Resolution Requirements (px/mm) and Sensor Trade-Offs (Open Question #2)

Measured Results: Published automated insect imaging systems establish exact empirical resolution tiers in $\text{px/mm}$. At the low end, smartphone photos of full yellow sticky cards at $10\text{ px/mm}$ (https://wildlabs.net/en/discussion/detecting-thrips-and-larger-insects-together?language_content_entity=en) and video tracking at $10.24\text{ px/mm}^2$ ($\approx 3.2\text{ px/mm}$ linear, https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0239504) were explicitly reported by practitioners to fail at reliable YOLO pest identification on sticky cards. By contrast, $16\text{ px/mm}$ is the validated standard resolution of LEPMON (https://preprints.arphahub.com/download/pdf/, https://www.researchgate.net/figure/Results-of-dataset-construction-Three-datasets-regarding-the-taxonomic-levels-order_fig2_366713152) for automated time-lapse AI identification of nocturnal Lepidoptera (ranging from $3\text{ mm}$ microlepidoptera to large moths) on planar targets. Sticky Pi (https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3001689) operates at $20.5\text{ px/mm}$ ($1944 \times 2592\text{ px}$ across a $126 \times 126\text{ mm}$ sticky card) to classify Drosophila suzukii and bycatch across 17 taxa at $83.1\%$ accuracy, while Mothbox (https://www.biorxiv.org/content/10.64898/2025.12.03.692171v1.full-text) uses a $64\text{ MP}$ camera ($9248 \times 6944\text{ px}$) over a $290 \times 205\text{ mm}$ target sheet at $30\text{ cm}$ to achieve $25\text{ px/mm}$, readily identifying insects $>3\text{ mm}$ to family and morphospecies level. Higher resolutions of $30–36\text{ px/mm}$ are used for multi-pest sticky traps including $1–2\text{ mm}$ whiteflies (https://wildlabs.net/en/discussion/detecting-thrips-and-larger-insects-together?language_content_entity=en) and museum habitus drawer scanners (https://pmc.ncbi.nlm.nih.gov/articles/PMC6988528/, https://zookeys.pensoft[span_43](start_span)[span_43](end_span)[span_48](start_span)[span_48](end_span).net/article_preview.php?id=2915&skip_redirect=1, resolving $0.06–0.10\text{ mm}$ structures and reaching $74.6\%$ species recall at a $0.5$ threshold), while $50–83\text{ px/mm}$ is reserved for $1–2\text{ mm}$ thrips (https://www.jstage.jst.go.jp/article/agrmet/advpub/0/advpub_D-25-00011/1/_html/-char/ja) and macro lab dishes (https://www.osti.gov/servlets/purl/2425703).

System / Configuration	Field of View (mm)	Active Sticky Card Coverage (%)	Spatial Resolution (\text{px/mm})	Footprint of OFM (4.5–7\text{ mm})	Footprint of CM (7.6–12\text{ mm})	Primary Source URL
Smartphone Full-Card (Failure Floor)	100 \times 300\text{ mm}	100.0\%	10.0\text{ px/mm}	45–70\text{ px}	76–120\text{ px}	https://wildlabs.net/en/discussion/detecting-thrips-and-larger-insects-together?language_content_entity=en
Orchard Sentinel OV5640 (Full Liner)	198 \times 174\text{ mm}	100.0\%	13.1\text{ px/mm}	59–92\text{ px}	100–157\text{ px}	uploaded:00_ARGON_BRIEF.md
Orchard Sentinel OV5640 (Active Grid)	175 \times 174\text{ mm}	100.0\% (glue)	14.8\text{ px/mm}	67–104\text{ px}	112–178\text{ px}	uploaded:00_ARGON_BRIEF.md
Orchard Sentinel Baseline (README Grid)	Calibrated grid	Baseline	15.3\text{ px/mm}	69–107\text{ px}	116–184\text{ px}	uploaded:00_ARGON_BRIEF.md
LEPMON Automated Moth Trap	Nocturnal target	100.0\%	16.0\text{ px/mm}	72–112\text{ px}	122–192\text{ px}	https://preprints.arphahub.com/article/214480/download/pdf/
Orchard Sentinel OV3660 (Current Narrow)	115 \times 85\text{ mm}	28.4\% (71.6\% blind)	17.8\text{ px/mm}	80–125\text{ px}	135–214\text{ px}	uploaded:00_ARGON_BRIEF.md
Sticky Pi Smart Trap (5 MP)	126 \times 126\text{ mm}	100.0\%	20.5\text{ px/mm}	92–144\text{ px}	156–246\text{ px}	https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3001689
Mothbox Automated Trap (64 MP)	290 \times 205\text{ mm}	100.0\%	25.0\text{ px/mm}	113–175\text{ px}	190–300\text{ px}	https://www.biorxiv.org/content/10.64898/2025.12.03.692171v1.full-text
ANIC / Naturalis Museum Drawers	480 \times 500\text{ mm}	100.0\%	35.0–36.0\text{ px/mm}	158–252\text{ px}	266–432\text{ px}	https://pmc.ncbi.nlm.nih.gov/articles/PMC6988528/

Engineering Analysis and Opinion (Answering Open Question #2): Separating CM ($7.6–12.0\text{ mm}$ body) from OFM ($4.5–7.0\text{ mm}$ body) on glue relies on two physical cues: the $2.5–3.5\text{ mm}$ mean body-length differential (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf) and CM's $1.5 \times 2.0\text{ mm}$ coppery-bronze apical patch and $0.25–0.35\text{ mm}$ wavy forewing striae (https://bettertermite.com/pests/moths/codling-moths/). Resolving a $0.3\text{ mm}$ striation wave and a $1.5\text{ mm}$ bronze speculum after Bayer demosaicing and JPEG compression requires $14–16\text{ px/mm}$ (Confidence: Sure, matching the $16\text{ px/mm}$ LEPMON Lepidoptera standard, https://preprints.arphahub.com/article/214480/download/pdf/). At $15\text{ px/mm}$, a $2.5\text{ [span_103](start_span)[span_103](end_span)[span_107](start_span)[span_107](end_span)mm}$ body-length gap between CM and OFM equals $37.5\text{ pixels}$, which is effortlessly resolved once ArUco scale calibration is active. When comparing the narrow OV3660 ($\sim 17.8\text{ px/mm}$ over the middle $28.4\%$ of the card) against the wide OV5640 ($5\text{ MP}$, $2592 \times 1944\text{ px}$) covering the full active sticky grid, the wide OV5640 wins decisively (Confidence: Sure). Because $174 \times 22\text{ mm}$ of the $174 \times 198\text{ mm}$ liner is a non-sticky printed header (uploaded:00_ARGON_BRIEF.md), framing the $2592 \times 1944\text{ px}$ OV5640 across the $174 \times 175\text{ mm}$ active $7 \times 7$ grid (plus narrow tray lips for ArUco markers) delivers $14.0–14.8\text{ px/mm}$ across $100\%$ of the glue surface—eliminating the $71.6\%$ blind spot while keeping every target moth $67–178\text{ px}$ long.

Foundation-Model Embeddings (BioCLIP, DINOv2, BIOSCAN-CLIP): Linear Probe vs. Fine-Tuning

Measured Results: BioCLIP (https://arxiv.org/abs/2311.18803, https://huggingface.co/imageomics/bioclip/blob/refs%2Fpr%2F11/README.md) is a ViT-B/16 vision-language foundation model initialized from OpenAI CLIP and trained on TreeOfLife-10M ($10\text{M}$ images across $454,103$ taxa), achieving a $+17.5\%$ average accuracy improvement over original CLIP in zero-shot classification, $+16.7\%$ in 1-shot, and $+17.3\%$ in 5-shot scenarios (https://www.alphaxiv.org/abs/2311.18803). BIOSCAN-CLIP (https://arxiv.org/html/2406.12723v1, https://proceedings.neurips.cc/paper_files/paper/2024/file/3fdbb472813041c9ecef04c20c2b1e5a-Paper-Datasets_and_Benchmarks_Track.pdf) aligns RGB images, DNA barcodes, and taxonomic labels across $5,150,850$ arthropod specimens ($98\%$ insects), excelling on standardized dorsal laboratory crops.

A landmark 2026 study on agroforestry sticky-trap pest crops (https://arxiv.org/html/2609.30278v1) directly compared frozen foundation-model linear probing against full fine-tuning across within-domain and Leave-One-Site-Out (Region LOSO) splits. While within-domain accuracy reached $0.934$ for DINOv2 and $0.955$ for ImageNet-ViT (FT), under regional/trap domain shift (Wakayama LOSO evaluation split) BioCLIP full fine-tuning collapsed to $0.628$ (a catastrophic $-0.270$ degradation), and ImageNet-ViT (FT) dropped by $-0.162$, whereas DINOv2 retained $0.803$ accuracy (https://arxiv.org/html/2609.30278v1). Furthermore, calibration degraded under domain shift, with the Wakayama linear probe Expected Calibration Error ($\text{ECE} = 0.078$) exceeding Mie's ($\text{ECE} = 0.054$). Crucially, applying selective prediction (uncertainty-aware confidence triage) to the frozen BioCLIP logistic probe recovered Wakayama accuracy from $0.593$ (at $100\%$ coverage) to $0.815$ at $50\%$ coverage; in the high-confidence band $[0.9, 1.0)$, the human correction rate was only $1.15\%$ ($95\%\text{ CI}: [0.53, 2.48]\%$), compared to $68.0\%$ in the $[0, 0.5)$ band (https://arxiv.org/html/2609.30278v1). When larger target-lineage datasets are available, bioRxiv 2026.04.28.721370v3 (https://www.biorxiv.org/content/10.64898/2026.04.28.721370v3.full-text) showed that ArcFace metric fine-tuning restored linear-probe accuracy to $>0.93$ and $\text{mAP} > 0.83$, while BioAnalyst (https://openreview.net/pdf/0baefc45ec35a93137f303dc0a24ee85d57fd039.pdf) demonstrated that VeRA adapters (using one-tenth the learnable parameters of LoRA) matched or outperformed LoRA fine-tuning.

Classifier Configuration	Within-Domain Accuracy	Cross-Region / Trap LOSO Accuracy (Wakayama)	Domain-Shift Degradation (\Delta)	Calibration / Triage Recovery Notes	Primary Source URL
BioCLIP Full Fine-Tuning (ViT-B/16)	0.898	0.628	-0.270	Overfits to training trap/region background features	https://arxiv.org/html/2609.30278v1
ImageNet-ViT Full Fine-Tuning	0.955	0.793	-0.162	Substantial cross-site drop despite high in-domain score	https://arxiv.org/html/2609.30278v1
DINOv2 Configuration	0.934	0.803	-0.131	Strongest single-model cross-region feature invariance	https://arxiv.org/html/2609.30278v1
Frozen BioCLIP + Logistic Probe (100% Cov.)	High baseline	0.593	Baseline probe	\text{ECE} = 0.078 on Wakayama vs. 0.054 on Mie	https://arxiv.org/html/2609.30278v1
Frozen BioCLIP Probe + 50% Selective Triage	High baseline	0.815	+0.222 recovery	Only 1.15\% error in [0.9, 1.0) band vs. 68.0\% in [0, 0.5)	https://arxiv.org/html/2609.30278v1
SSL Backbone + ArcFace Fine-Tuning	Closed-set level	>0.930\text{ LP Acc}	\text{mAP} > 0.83, \text{ARI} > 0.76	Requires multi-sample lineage dataset (n > 10/species)	https://www.biorxiv.org/content/10.64898/2026.04.28.721370v3.full-text

Engineering Analysis and Opinion: The Orchard Sentinel team's decision in classify.py to use frozen BioCLIP embeddings with a linear head rather than full ViT fine-tuning is empirically validated and must be retained for this season (Confidence: Sure). Because the project's OFM training crops come from a single physical trap (uploaded:00_ARGON_BRIEF.md), unfreezing the ViT-B/16 backbone causes the network to overwrite its pre-trained biological features and memorize the exact cardboard grain, glue thickness, and lighting gradient of that single trap (https://arxiv.org/html/2609.30278v1). However, a raw 512-dimensional BioCLIP linear probe exhibits a critical architectural blind spot: open_clip's preprocess_val (https://huggingface.co/imageomics/bioclip/blob/refs%2Fpr%2F11/README.md) resizes every bounding-box crop to $224 \times 224\text{ pixels}$ ($299 \times 299$ in older Inception pipelines, https://pmc.ncbi.nlm.nih.gov/articles/PMC6988528/), completely erasing absolute physical size! Inside a $224 \times 224$ tensor, a $5.0\text{ mm}$ OFM and a $10.0\text{ mm}$ CM occupy the exact same pixel dimensions. To restore physical size discrimination, classify.py must concatenate explicit scale-calibrated morphological features—specifically $[\text{length\_mm}, \text{width\_mm}, \sqrt{\text{area\_mm}^2}, \text{aspect\_ratio}, \text{solidity}]$ (standardized via z-score, https://www.biorxiv.org/content/10.1101/2023.12.05.570242v2.full-text)—directly to the L2-normalized 512-D BioCLIP embedding vector before feeding the 517-D vector into the L2-regularized Logistic Regression head.

Hierarchical and Open-Set Classification for Non-Target Moths (other_moth)

Measured Results: In commercial orchards, pheromone traps capture numerous non-target tortricids (LAW, Acleris, Archips, Epinotia) and Diptera/Hymenoptera bycatch (https://opdmc.org/wp-conte[span_4](start_span)[span_4](end_span)nt/uploads/2015/12/2016_Abstracts.pdf, https://www.uvm.edu/femc/attachments/project/999/reports/Torticidae.pdf). The Open-Insects benchmark (https://arxiv.org/html/2503.01691v1, https://neurips.cc/virtual/2025/poster/121829, https://huggingface.co/datasets/yuyan-chen/open-insect) systematically evaluated Open-Set Recognition (OSR) and Out-of-Distribution (OOD) detection for insects across Northeastern North America, Western Europe, and Central America across three method families: post-hoc scoring, training-time regularization, and training with auxiliary data. The benchmark established three key findings: first, detecting local open-set species (OOD-L)—sympatric look-alike moths from the same geographic region—is substantially harder (yielding lower AUROC and TPR@FPR) than detecting non-local species (OOD-NL) or non-moth insects (OOD-NM) (https://neurips.cc/virtual/2025/poster/121829). Second, post-hoc Maximum Softmax Probability (MSP) and its logit derivatives remain among the strongest baselines without requiring network retraining (https://arxiv.org/html/2503.01691v1). Third, Outlier Exposure (training with auxiliary open-set species) significantly improves OOD rejection of local look-alikes (https://arxiv.org/html/2503.01691v1). Additionally, in habitus CNN classification (https://www.researchgate.net/publication/338152771_Species-level_image_classification_with_convolutional_neural_network_enables_insect_identification_from_habitus_images), applying a $0.5$ probability threshold to back off from species to genus/family level increased recall from $50.7\%$ to $74.6\%$, while support-derived multi-prototypes (https://openreview.net/forum?id=RAXtDvPxes) further improved hierarchical few-shot open-set insect recognition.

Engineering Analysis and Opinion: A flat 6-class closed-set softmax classifier (CM, OFM, OBLR, other_moth, other_insect, debris) trained on a small sample of other_moth crops will misclassify novel orchard tortricids as CM or OFM with high softmax confidence (Confidence: Sure). The Orchard Sentinel pipeline should restructure classify.py into a Two-Tier Hierarchical Open-Set Classifier with Outlier Exposure and Lure Priors. In Tier 1 (Coarse Taxonomic Gate), the model separates debris, other_insect (non-Lepidoptera), and Lepidoptera using BioCLIP's native hierarchical representation (https://arxiv.org/html/2311.18803v3). In Tier 2 (Target Tortricid vs. Open-Set other_moth), the other_moth training bucket should be augmented with $500–1,000$ Auxiliary Outlier Exposure crops of Northeastern North America Tortricidae (Grapholita prunivora, Acleris, Archips, Epinotia) drawn from the Open-Insects NE-America split (https://huggingface.co/datasets/yuyan-chen/open-insect) and AMI-Traps (https://zenodo.org/records/11358689). At inference time, if a crop's temperature-scaled MSP is $< 0.75$ (https://arxiv.org/html/2609.30278v1), or if its predicted species mismatches the trap's known pheromone lure (uploaded:00_ARGON_BRIEF.md) with probability $< 0.92$, the track should be flagged as unsure and routed to the human review queue.

Domain Shift Between Traps and Regions and Proven Fixes

Measured Results: Multi-device and multi-color sticky trap studies (https://pmc.ncbi.nlm.nih.gov/articles/PMC11327826/) and regional LOSO evaluations (https://arxiv.org/html/2609.30278v1) demonstrate that covariate shift arises from camera sensor differences, sticky-liner chromaticity, and illumination color cast. In arXiv:2609.30278v1 (https://arxiv.org/html/2609.30278v1), human inter-annotator agreement across all 13 raw sticky-trap categories was $77.7\%$ (Cohen's $\kappa = 0.687$), rising to $94.8\%$ ($\kappa = 0.900$) when restricted to identifiable species crops excluding ambiguous/damaged specimens.

Engineering Analysis and Opinion: To break the single-trap background shortcut on OFM (uploaded:00_ARGON_BRIEF.md) before a second field trap's data is acquired (Confidence: Sure), the training script (ml/train_v1.py) should apply Foreground Segmentation + Cross-Trap Background Blending (https://spiral.imperial.ac.uk/server/api/core/bitstreams/afebbaa6-026a-48f2-94aa-89314b8ea80f/content). By separating each dark moth body from its bright sticky-liner background via adaptive luminance thresholding and Poisson-blending (cv2.seamlessClone) the moth foreground onto random empty background patches sampled from CM and OBLR traps, the linear probe is forced to learn wing-scale and morphological features rather than the background glue tint of the single OFM trap. Simultaneously, dividing each crop's RGB channels by the median RGB value of its surrounding $50\text{ px}$ local liner background ring neutralizes trap-to-trap LED and skylight color shifts (https://academic.oup.com/aesa/article/99/5/865/12163).

3. Data Strategy: Public Datasets, Synthetic Copy-Paste, Active Learning, and Sample Complexity

Public Sticky-Trap and Lepidopteran Datasets

Twelve publicly available datasets provide annotated sticky-trap scenes, in-situ camera-trap moth crops, and Northeastern North American open-set look-alikes suitable for bootstrapping Orchard Sentinel's detector and classifier:

Dataset Name	Content & Relevance to Orchard Sentinel	Size / Annotations	License	Direct URL / DOI
AMI Dataset (AMI-GBIF & AMI-Traps)	Nocturnal moths in NE North America, Europe & Central America; includes both citizen-science and in-situ automated camera trap crops	\sim 2.5\text{M} GBIF images; 2,893+ trap images with multi-label moth bboxes	CC BY 4.0 (Data) / AGPL-3.0 (Code)	https://zenodo.org/records/11358689 & https://github.com/orgs/RolnickLab/repositories
Open-Insects Benchmark	Curated closed-set, Local OOD (OOD-L), Non-Local OOD, and Non-Moth splits for NE North America	Derived from AMI-GBIF + regional OOD splits	CC BY 4.0	https://huggingface.co/datasets/yuyan-chen/open-insect (https://arxiv.org/html/2503.01691v1)
TreeOfLife-10M (BioCLIP)	Largest ML-ready biology dataset integrating iNat21, BIOSCAN-1M, and EOL with full 7-rank taxonomy	>10\text{M} images across 454,103 taxa	MIT (Weights/Code)	https://huggingface.co/imageomics/bioclip (https://arxiv.org/abs/2311.18803)
Sticky Pi Dataset	High-frequency (20\text{ min} cadence) field sticky-card images for Universal Insect Detector & Siamese Matcher	Field time-series across 70 device-weeks; 17+ taxa polygon masks	CC BY 4.0	https://doi.org/10.5281/zenodo.4680119 (https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3001689)
4TU.ResearchData Yellow Sticky Traps & GinJinn2	Greenhouse yellow glue traps with annotated insects (whiteflies, Nesidiocoris, Macrolophus)	379 raw full-res images; 120 COCO-annotated subset (GinJinn2)	CC0 1.0 Public Domain	https://doi.org/10.4121/uuid:8b8ba63a-1010-4de7-a7fb-6f9e3baf128e & https://data.bgbm.org/dataset/gfbio/0036/
PeMaToEuroPep (Flat Bug)	Sticky-card images from Kaggle (friso1987) annotated with instance polygons via SAM	284 sticky-card images with COCO polygon JSON	CC0 1.0 Public Domain	https://zenodo.org/records/13930055 (https://doi.org/10.5281/zenodo.13930055)
Pest Sticky Traps (PST)	Chromotropic sticky-trap images designed for pest density and counting evaluation	Full sticky-card images with point/box labels	CC BY 4.0	https://zenodo.org/records/7801239 (https://data.europa.eu/data/datasets/oai-zenodo-org-7801239?locale=en)
Multi-Color & Multi-Device Sticky Trap Dataset	Pests on white, transparent, yellow, and blue sticky traps across 3 cameras (DSLR & phones)	Lab and field sticky trap images with device/color metadata	CC BY 4.0	https://doi.org/10.6084/m9.figshare.23617383.v2 (https://pmc.ncbi.nlm.nih.gov/articles/PMC11327826/)
Grapevine Sticky Trap Dataset	Field sticky cards with leafhopper pests (Scaphoideus titanus, Orientus ishidae) in YOLO format	>600 images, \sim 1,500 annotations per class	CC BY 4.0	https://zenodo.org/records/11441757 (https://pmc.ncbi.nlm.nih.gov/articles/PMC11669504/)
BMSB Sticky Trap Dataset	Brown marmorated stink bug (Halyomorpha halys) and bycatch on field sticky traps	Two sub-datasets of field sticky trap imagery	CC BY 4.0	https://zenodo.org/records/14051319
IP102 Benchmark	Hierarchical agricultural pest recognition & detection dataset across 8 crops	75,222 images (19,000 with detection bounding boxes) across 102 classes	Free for academic use (Meta-Album CC BY-NC 4.0)	https://github.com/xpwu95/IP102 (https://meta-album.github.io/datasets/INS_2.html)
Pest24 Dataset	Large-scale dense multi-target small agricultural pest trap dataset (including tortricids/noctuids)	25,378 images with >190,000 labeled instances across 24 classes	CC BY 4.0	https://github.com/jlauwcj/pest-pvt (https://www.mdpi.com/2073-4395/15/9/2022)

Synthetic Copy-Paste Augmentation: When It Helps and When It Hurts

Measured Results: Copy-Paste augmentation—extracting segmented insect foregrounds and compositing them onto background trap scenes—is widely validated for object detection and instance segmentation in agricultural pest monitoring (https://www.mdpi.com/2075-4450/17/7/715, https://pmc.ncbi.nlm.nih.gov/articles/PMC11766181/, https://ieeexplore.ieee.org/document/11567066/, https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2026.1940983/full). In Insects 2026, 17(7), 715 (https://www.mdpi.com/2075-4450/17/7/715), combining multi-scale feature fusion with a copy-paste/cut-up paradigm for dense pests improved $\text{AP@0.5}$ by $+6.9\text{ percentage points}$ to $67.1\%$. In Smart Agricultural Technology 2023 (https://spiral.imperial.ac.uk/server/api/core/bitstreams/afebbaa6-026a-48f2-94aa-89314b8ea80f/content, "Generate-Paste-Blend-Detect"), Giakoumoglou et al. demonstrated a critical failure mode of naive copy-paste: simply pasting insect masks onto background images introduces sharp boundary pixel artifacts that convolutional networks memorize. Applying Poisson blending (or Gaussian boundary feathering) eliminated boundary artifacts and seamlessly mixed object illumination with the sticky-card background (https://spiral.imperial.ac.u[span_230](start_span)[span_230](end_span)k/server/api/core/bitstreams/afebbaa6-026a-48f2-94aa-89314b8ea80f/content, https://pmc.ncbi.nlm.nih.gov/articles/PMC9523729/). Furthermore, AgriEngineering 2026 (https://www.mdpi.com/2624-7402/8/4/138) underscores that copy-paste augmentation must be applied strictly to the training split after partitioning, leaving validation and test images unaugmented to prevent data leakage.

Engineering Analysis and Opinion: A strict distinction must be drawn between Copy-Paste for Detection and Copy-Paste for Species Classification (Confidence: Sure). For training a 1-class YOLOv8n/YOLOv11n detector (detect.py replacement), Copy-Paste is highly effective: pasting real sticky-trap moth cutouts onto empty or lightly populated Orchard Sentinel liner photos—specifically placing moths across printed $25\text{ mm}$ grid intersections and in touching pairs using Poisson blending (cv2.seamlessClone)—rapidly teaches the detector to localize moths over grid lines without requiring thousands of real field captures (https://spiral.imperial.ac.uk/server/api/core/bitstreams/afebbaa6-026a-48f2-94aa-89314b8ea80f/content, https://www.mdpi.com/2073-431X/14/8/327). Conversely, for training the species classifier (classify.py), pasting clean, dry museum or citizen-science moths from iNaturalist or AMI-GBIF onto sticky liner backgrounds does NOT bridge the domain gap (Confidence: Sure), because citizen-science photos depict live moths resting on bark or sheets with pristine dry scales, whereas delta-trap moths are soaked in translucent polybutene glue (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf) and lit by a close-range ESP32 LED inside a red plastic enclosure. However, cross-pasting real sticky-liner OFM cutouts onto background patches from CM and OBLR traps directly improves classifier generalization by breaking the single-trap background shortcut (uploaded:00_ARGON_BRIEF.md).

Active Learning and Real Labelled Sample Requirements per Class

Measured Results: Iterative active learning frameworks on sticky traps—such as DDU-BiATeacher (https://www.researchgate.net/publication/363938538_Using_Deep_Learning_for_Detection_and_Classificatio[span_226](start_span)[span_226](end_span)[span_228](start_span)[span_228](end_span)n_of_Insects_on_Traps), grapevine sticky-trap active surveillance (https://www.mdpi.com/2073-431X/14/8/327, https://www.researchgate.net/publication/387414378_A_novel_d[span_163](start_span)[span_163](end_span)ataset_and_deep_learning_object_detection_benchmark_for_grapevine_pest_surveillance), greenhouse sticky-trap active loops (https://research.monash.edu/files/389022168/375792464_oa.pdf), and camera-trap incremental loops (https://www.biorxiv.org/content/10.1101/2023.12.05.570242v2.full-text, https://arxiv.org/html/2406.12452v1)—initialize a detector/classifier on a small seed set, deploy it to unlabeled trap streams, and query human experts only on high-uncertainty or disagreement samples. In arXiv:2609.30278v1 (https://arxiv.org/html/2609.30278v1), uncertainty-aware triage showed that human correction was required on $68.0\%$ of crops with confidence $<0.5$, but only $1.15\%$ of crops with confidence $\ge 0.9$. Across published insect classification and detection studies, empirical sample complexity falls into four distinct regimes:

Target Task & Architecture	Typical Real Labelled Examples Needed per Class	Empirical Performance & Failure Thresholds	Primary Source URL
Few-Shot Foundation Probe (BioCLIP k-NN / Zero-Shot)	1\text{ to }10 specimens / class	Beats CLIP by +16.7\% to +17.5\%, but at n = 10 per species diversity/classification errors remain elevated	https://www.biorxiv.org/content/10.64898/2026.04.28.721370v3.full[span_183](start_span)[span_183](end_span)-text & https://www.alphaxiv.org/abs/2311.18803
Regularized BioCLIP + Calibrated Size Linear Probe	30\text{ to }60 unique tracked individuals / class (across \ge 3 traps)	Reaches >81.5–90.0\% cross-trap accuracy when paired with 50\% confidence triage	https://arxiv.org/html/2609.30278v1 & https://pmc.ncbi.nlm.nih.gov/articles/PMC13513098/
1-Class (insect) Nano Detector (YOLOv8n / YOLOv11n)	100\text{ to }300 annotated sticky cards (1,000–3,000 total insect boxes)	Converges to >90\%\text{ mAP@0.5} for class-agnostic insect localization on sticky cards	https://zenodo.org/records/13930055 & https://www.osti.gov/servlets/purl/2425703
End-to-End Multi-Class CNN / ViT / DETR from Scratch	700\text{ to }1,500+ real specimens / class (2,837 for DETR crop tool)	Required to avoid overfitting when learning fine-grained wing features without a foundation prior	https://www.kaggle.com/datasets/rtlmhjbn/ip02-dataset & https://pmc.ncbi.nlm.nih.gov/articles/PMC11669504/

Engineering Analysis and Opinion: The Orchard Sentinel server already includes a Review Queue (uploaded:00_ARGON_BRIEF.md). To transform this review queue into a high-efficiency Active Learning Engine, the review selection policy should query entire tracks rather than isolated frames, prioritizing three triggers (Confidence: Sure): (1) any unreviewed track of CM, OFM, or OBLR occurring prior to a block's established biofix date that would contribute to triggering the NEWA sustained-catch rule ($\ge 2$ moths); (2) any track exhibiting high temporal class entropy across consecutive frames (e.g., oscillating between CM and OFM); and (3) tracks whose mean confidence falls in the $[0.35, 0.75)$ uncertainty band (https://arxiv.org/html/2609.30278v1).

4. Counting Over Time: Change Detection vs. Tracking, Decay, and Error Estimation

Change Detection Between Consecutive Photos vs. Multi-Frame Tracking (Open Question #4)

Measured Results: Automated sticky-trap systems in both commercial deployment and academic literature combine consecutive-frame comparison with multi-frame instance matching. In the commercial Trapview platform (https://open-research-europe.ec.europa.eu/articles/6-421, https://legacy.trapview.com/trapview_help/html/device_events.html), moth retention and new captures are evaluated by comparing detections across consecutive images (supported by a "Compare with pre[span_184](start_span)[span_184](end_span)vious" unmarked image toggle in the review UI) while logging explicit device events ("change of sticky plate", "sticky roll tweak" self-cleaning roll advance, "change of lure") to segment monitoring periods. In academic literature, Sticky Pi (https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3001689, https://www.biorxiv.org/content/10.1101/2021.08.11.455750v1.full) captures an image every $20\text{ minutes}$ ($\sim 500$ images/week) and executes a three-stage time-series workflow: a per-frame Universal Insect Detector, a Siamese Insect Matcher that links instances across consecutive frames based on visual embedding similarity, centroid displacement, and $\Delta t$ to construct a multi-frame "tuboid" (track), and an Insect Tuboid Classifier that aggregates class probabilities across the tuboid. Similarly, automated camera traps (https://www.biorxiv.org/content/10.1101/2023.12.05.570242v2.full-text) enforce minimum track-length persistence filters (-min_tracks 3) to reject transient non-captured visitors walking across the frame.

Handling Insects That Shift, Decay, Get Covered, or Get Scavenged

Measured Results: Field time-lapse studies document four physical processes that violate the static-object assumption on sticky liners. First, in infrared time-lapse studies of tortricid pheromone traps (https://www.researchgate.net/figure/A-Three-consecutive-photographs-taken-by-the-IR-camera-the-fi-rst-two-were-taken-before_fig3_355318381), researchers documented that entrapped male moths remain alive for several hours and periodically shift position or rotate on the sticky card across consecutive photographs. Second, in multi-country field trials of Trapview vs. conventional sticky traps (https://open-research-europe.ec.europa.eu/articles/6-421), linear regression between total trap catch and moth movement rate ($\%$) demonstrated that as total catch increases (trap saturation), the exposed sticky glue area shrinks, causing newly arriving moths to walk across earlier catches or escape. Third, the same study (https://open-research-europe.ec.europa.eu/articles/6-421) documented active predation and scavenging on captured moths inside automated traps, leaving detached wings, antennae, and partial moth remains. Fourth, over days on the trap, polybutene glue wicks into wing scales, turning patterned forewings solid black (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf).

Engineering Analysis and Opinion (Answering Open Question #4): Pure pixel-level frame differencing ($I_t - I_{t-1}$) between consecutive photos fails in orchard delta traps (Confidence: Sure) because wind swings the hanging trap (https://www.researchgate.net/figure/A-Three-consecutive-photographs-taken-by-the-IR-camera-the-fi-rst-two-were-taken-before_fig3_355318381), shifting sunlight beams across the red roof, and because a newly caught moth that struggles and crawls $8\text{ mm}$ between frame $t-1$ and frame $t$ produces both a "disappearance" at $(x_1, y_1)$ and a false "new arrival" at $(x_2, y_2)$, double-counting the insect. Conversely, weighting all frames equally across a 3-week track in track.py (uploaded:00_ARGON_BRIEF.md) allows 80 frames of a glue-blackened, decayed, or partially scavenged carcass (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf, https://open-research-europe.ec.europa.eu/articles/6-421) to outvote the first 4 frames when the moth's coppery wing-tip or oblique bands were fresh and diagnostic.

The optimal architecture for track.py combines ArUco-Aligned Track-by-Detection with Freshness-Frozen Consensus (Confidence: Sure):

1. Two-Tier Bipartite Association Gate: After registering frame $t$ via the 4 corner ArUco markers, match detections $D_t$ to active tracks $T_{t-1}$ via the Hungarian algorithm. For mature tracks (age $> 24\text{ hours}$, insect is dead and immobile), enforce a tight spatial gate ($\Delta d \le 3.5\text{ mm}$). For fresh tracks (age $\le 24\text{ hours}$, insect may still struggle and crawl in the glue, https://www.researchgate.net/figure/A-Three-consecutive-photographs-taken-by-the-IR-camera-the-fi-rst-two-were-taken-before_fig3_355318381), allow a wider spatial gate ($\Delta d \le 18.0\text{ mm}$) gated by BioCLIP cosine similarity ($>0.80$) and size consistency ($\pm 15\%$) so a crawling moth is linked to its existing track rather than counted twice.

2. Freshness-Weighted Species Consensus: Compute a track's species consensus exclusively from the first $K = 5$ glare-free, non-occluded frames after initial detection (weighted by $w_k = \text{confidence}_k \times \exp(-0.2 k)$), and freeze the track's species label once it reaches high confidence or human review. If a track later vanishes (e.g., scavenged by a wasp or covered by a new moth landing on top, https://open-research-europe.ec.europa.eu/articles/6-421), retain the historical track in the cumulative liner count so weekly catch never decreases backward.

3. Automatic Detection of Unannounced Liner Swaps (Open Question #4b): When a scout or grower replaces a sticky liner without pressing the physical reset button (uploaded:00_ARGON_BRIEF.md), track.py should detect this automatically via a Vanishing-Track Cohort Rule: if a liner has $N_{\text{active}} \ge 2$ established tracks (each seen in $\ge 3$ frames) and $\ge 80\%$ of those established tracks disappear simultaneously in frame $t$ (confirmed across frame $t+1$ while mean card brightness confirms the lens is unobstructed), the server automatically triggers a new_liner_detected event, archives the previous card's tracks, and resets the liner age counter (uploaded:00_ARGON_BRIEF.md, https://legacy.trapview.com/trapview_help/html/device_events.html).

Estimating Count Error and Propagating Uncertainty

Measured Results: In Zenodo 22922085 (https://zenodo.org/records/22922085) and J. Agric. Meteorol. 2025 (https://www.jstage.jst.go.jp/article/agrmet/advpub/0/advpub_D-25-00011/1/_html/-char/ja), automated sticky-trap count error increases non-linearly with placement duration and trap density, reaching an RMSE of $11.3$ insects ($\text{NRMSE} = 19.8\%$) on long-duration cards.

Engineering Analysis and Opinion: Rather than displaying only a point integer count on the dashboard, the server can compute a calibrated $90\%$ prediction interval for each trap's weekly catch by summing the Bernoulli probabilities of all unreviewed tracks ($E[N] = N_{\text{reviewed}} + \sum_{i \in \text{unreviewed}} p_i$, with variance $\sigma^2 = \sum_{i \in \text{unreviewed}} p_i (1 - p_i)$) (Confidence: Likely). Whenever $E[N] \pm 1.645\sigma$ straddles an action threshold (such as the 5 moths/trap/week threshold for CM, https://extension.unh.edu/resource/fruit-ipm-reports), those specific unreviewed tracks should be boosted to the top of the human review queue.

5. Imaging and Optics: Glare Suppression, White Balance, Distortion, and Fiducials

Lighting Glossy Sticky Cards and Eliminating Specular Glare (Open Question #5)

Measured Results: In the Orchard Sentinel trap (uploaded:00_ARGON_BRIEF.md), a single unpolarized white LED illuminates the glossy polybutene sticky liner inside the $110\text{ mm}$ roof apex, blowing out $10–13\%$ of the card area with saturated specular glare. Optical engineering and macro-imaging studies (https://fjwoptical.com/blogs/blog/lighting-the-[span_185](start_span)[span_185](end_span)role-of-polarized-lighting-in-reducing-glare-and-reflections, https://petapixel.com/2021/01/19/cross-polarization-what-it-is-and-why-it-matters/, https://docs.sharktacos.com/photography/xpol.html, https://www.venuslens.net/cross-polarized-macro-photography/, https://onlsol.com/uncategorized/glare-reduction-and-polarizers/) establish the physical mechanism separating specular glare from useful image signal. When light strikes the glossy glue layer and shiny chitinous insect cuticles, specular reflection bounces directly off the air-glue interface like a mirror, preserving the linear polarization state of the incident light source and saturating sensor pixels to $[255, 255, 255]$ (https://fjwoptical.com/blogs/blog/lighting-the-role-of-polarized-lighting-in-reducing-glare-and-reflections, https://www.venuslens.net/cross-polarized-macro-photography/). Conversely, light that penetrates into the moth's wing scales and cardboard fibers undergoes multiple internal scatterings (diffuse reflection), which randomly depolarizes the light and carries the true pigment and structural color information (https://fjwoptical.com/blogs/blog/lighting-the-role-of-polarized-lighting-in-reducing-glare-and-reflections). Placing a linear polarizer film over the LED illumination source and a second linear polarizer over the camera lens rotated at $90^\circ$ (orthogonal axes, cross-polarization) blocks specular surface glare while transmitting depolarized diffuse light (https://fjwoptical.com/blogs/blog/lighting-the-role-of-polarized-lighting-in-reducing-glare-and-reflections, https://docs.sharktacos.com/photography/xpol.html, https://www.researchgate.net/publication/270745491_Applying_Polarization-Based_Traps_to_Insect_Control). The documented trade-off (https://xanglecs.com/doc16/photogrammetry/cross-polarization) is a reduction in overall brightness ($\sim 1.5–2.0\text{ stops}$), requiring a modestly longer exposure time or higher LED drive current.

Engineering Analysis and Opinion (Answering Open Question #5 — Cheapest Proven Fix for Glare): Adding a translucent white plastic diffuser over the single LED (uploaded:00_ARGON_BRIEF.md) smooths illumination falloff across the card, but a diffuser alone does not eliminate specular reflection on flat glossy glue (Confidence: Sure). Because the camera looks straight down ($\theta \approx 0^\circ$) and the LED sits adjacent to the lens inside the narrow $110\text{ mm}$ apex, the flat glue layer acts as a mirror: a $30\text{ mm}$ diffuser simply turns a $15\text{ mm}$ saturated white dot into a $40\text{ mm}$ milky reflection that still washes out CM vs. OFM wing-tip contrast. The cheapest proven fix ($<\$0.50\text{/trap}$) combines a thin matte polycarbonate diffuser over the LED + a $10 \times 10\text{ mm}$ linear polarizer film over the LED ($0^\circ$) + an orthogonal $10 \times 10\text{ mm}$ linear polarizer film over the camera lens ($90^\circ$) (https://fjwoptical.com/blogs/blog/lighting-the-role-of-polarized-lighting-in-reducing-glare-and-reflections, https://docs.sharktacos.com/photography/xpol.html). Rotating the lens analyzer in live preview mode until the glue hotspot turns dark eliminates $>98\%$ of the $10–13\%$ glare blowout (uploaded:00_ARGON_BRIEF.md). For existing unpolarized photos, detect.py should compute a software glare mask in HLS color space (glare_mask = (L > 240) & (S < 30)), dilate by $5\text{ px}$, and reject any candidate blob with $>50\%$ area overlap inside glare_mask unless it matches an existing track established in a night frame.



White Balance Against the Alpha Scents Red Trap

Measured Results: Quantitative colorimetry of insect traps (https://academic.o[span_292](start_span)[span_292](end_span)[span_294](start_span)[span_294](end_span)up.com/aesa/article/99/5/865/12163) and multi-color trap datasets (https://pmc.ncbi.nlm.nih.gov/articles/PMC11327826/) prove that trap body color and lighting strongly shift RGB pixel values. During daytime captures (https://www.researchgate.net/figure/A-Three-consecutive-photographs-taken-by-the-IR-camera-the-fi-rst-two-were-taken-before_fig3_355318381), ambient sunlight penetrates the translucent red corrugated-plastic walls of the Alpha Scents delta trap (uploaded:00_ARGON_BRIEF.md), bathing the white liner in long-wavelength red light.

Engineering Analysis and Opinion: When the ESP32-S3 camera's onboard Auto White Balance (AWB) views the red-illuminated interior or red inner walls, it either fails to converge (leaving a heavy red/orange cast that makes gray OFM and CM moths look reddish-brown like OBLR) or over-corrects toward cyan (Confidence: Sure). Two changes resolve this permanently: in firmware (device/esp32-node/src/main.cpp), lock AWB to a fixed Daylight/LED preset (wb_mode = 1) after a $200\text{ ms}$ LED warm-up delay; and in server preprocessing (detect.py), sample the 90th-percentile RGB triplet $(R_w, G_w, B_w)$ from the glue-free $174 \times 22\text{ mm}$ white printed header strip (or the white quiet zones of the ArUco markers) to apply a diagonal Von Kries white-patch normalization $I'_{c} = I_{c} \times \frac{240}{C_w}$ across $c \in \{R, G, B\}$ (https://academic.oup.com/aesa/article/99/5/865/12163).

Lens Distortion Correction and ArUco/AprilTag Fiducials vs. the Printed Grid (Open Question #3)

Measured Results: In the Orchard Sentinel pipeline (uploaded:00_ARGON_BRIEF.md), the printed $25\text{ mm}$ grid finder misreads 5 of 10 insect-laden photos as $32–63\text{ px/mm}$ instead of $15.3\text{ px/mm}$, and the scale check locks in the wrong reading if a liner's first photo is misread. In camera-trap literature (https://www.biorxiv.org/content/10.1101/2023.12.05.570242v2.full-text, https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0239504), absolute physical insect size in $\text{mm}$ is computed reliably only when derived from fixed physical frame dimensions or dedicated calibration markers rather than occluded background grids.

Engineering Analysis and Opinion (Answering Open Question #3): The printed $25\text{ mm}$ grid is not a reliable primary scale reference (Confidence: Sure) because insects and glare break grid continuity and induce $2\times–4\times$ harmonic errors (uploaded:00_ARGON_BRIEF.md). The team should implement a two-step solution. First, as an immediate zero-hardware software patch in detect.py, clamp the scale estimate to the physical camera mount height (110 mm fixed apex $\to$ NOMINAL_PX_PER_MM = 15.3, bounded to [13.8, 16.8]), discarding any grid reading outside that ±10% window. Second, redesign hardware/scad/liner_tray.scad to $188\text{ mm}$ outer width (sliding cleanly inside the $195\text{ mm}$ floor) with four raised corner tabs holding $15 \times 15\text{ mm}$ matte-printed ArUco (cv2.aruco.DICT_4X4_50, IDs 0–3) or AprilTag (tag36h11) markers outside the glue zone (uploaded:00_ARGON_BRIEF.md). After removing radial barrel distortion via a precomputed cv2.initUndistortRectifyMap lookup table ($\sim 12\text{ ms}$ on Pi 5 CPU), detecting the 4 ArUco corners via cv2.aruco.ArucoDetector ($\sim 5\text{ ms}$) yields the exact perspective homography $H$ (cv2.getPerspectiveTransform), warping every photo into a canonical $15.0\text{ px/mm}$ top-down coordinate system and registering consecutive frames to within $\pm 0.5\text{ px}$ for track.py.

6. Evaluation Protocols, NEWA Phenology Rules, and Leak-Free Data Splits

Standard Evaluation Metrics Across Academic Papers and Commercial Systems

Measured Results: Rigorous evaluation of automated sticky-trap systems requires reporting metrics across four distinct levels (https://zenodo.org/records/22922085, https://www.preprints.org/manuscript/202609.1035/v1, https://arxiv.org/html/2609.30278v1): (1) Object Localization Metrics (Precision, Recall, F1-score, mAP@0.5, and mAP@[0.5:0.95], https://pmc.ncbi.nlm.nih.gov/articles/PMC11922902/, https://arxiv.org/html/2509.20318v2); (2) Per-Card and Weekly Count Error (Mean Absolute Error $\text{MAE}$, Root Mean Squared Error $\text{RMSE}$, Normalized RMSE $\text{NRMSE} = \text{RMSE}/\bar{C}$, and Pearson's $r$, https://www.preprints.org/manuscript/202609.1035/v1, https://www.jstage.jst.go.jp/article/agrmet/advpub/0/advpub_D-25-00011/1/_html/-char/ja); (3) Species Identification, Calibration, and Open-Set Metrics (Per-class Precision/Recall, Macro-F1 $\text{L-mF1}$, Expected Calibration Error $\text{ECE}$, Open-Set AUROC, and Selective Prediction Accuracy at coverage $c \in [0.5, 1.0]$, https://arxiv.org/html/2609.30278v1, https://arxiv.org/html/2503.01691v1); and (4) Phenological Decision Metrics, specifically Biofix Date Error ($|\hat{t}_{\text{biofix}} - t_{\text{biofix}}|$ in days) and Degree-Day Spray Window Offset ($|\Delta \text{DD}|$) (uploaded:00_ARGON_BRIEF.md, https://zenodo.org/records/22922085).

Exact NEWA Biofix and Degree-Day Rules (Answering Open Question #1)

Measured Results: Primary extension documentation from Cornell University's Network for Environment and Weather Applications (NEWA, https://newa.cornell.edu/crop-and-pest-management), Cornell Hudson Valley Research Lab (https://blogs.cornell.edu/jentsch/2019/06/08/plum-curculio-waining-codling-moth-waxing-residual-for-pc-needed-until-june-11th-highland-ny/, https://nyshs.org/wp-content/uploads/2017/12/Jentsch-Pages-27-32-from-NYFQ-Fall-Book-2017-4.pdf), New York State Horticultural Society (https://nyshs.org/wp-content/uploads/2016/10/Obliquebanded-Leafroller-Management-for-Apple-Production-Investigating-Strategies-for-Resistance-management-with-Emerging-Insecticide-Tools.pdf), UMass Extension (https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf), UNH Extension (https://extension.unh.edu/resource/fruit-ipm-reports), and Rutgers Cooperative Extension (https://plant-pest-advisory.rutgers.edu/fruit-ipm-updates-week-of-4-27-2026-2/, https://plant-pest-advisory.rutgers.edu/fruit-ipm-report-june-17-2025/) establish the exact phenological parameters required by phenology.py:

Pest Species	NEWA Biofix Rule	NEWA Degree-Day Method & Base Temp	Key Spray & Scouting Windows (Cumulative DD Post-Biofix)	Weekly Trap Action Threshold	Primary Extension Source URLs
Codling Moth (CM) Cydia pomonella	First sustained flight / catch (\ge 2 moths caught across consecutive trap checks)	Base 50^\circ\text{F} BE (Baskerville–Emin single-sine; 88^\circ\text{F} upper horizontal cutoff)	Gen 1: Rimon at 75–100\text{ DD}_{50}; Intrepid at 150\text{ DD}_{50}; 1st egg hatch / larvicides / virus at 200–250\text{ DD}_{50} & 550\text{ DD}_{50} (complete at 308\text{ DD}_{50} post-petal fall in low-pressure blocks). Gen 2: Hatch begins 1150–1260\text{ DD}_{50} & 1450–1550\text{ DD}_{50}.	5 moths / trap / week in apples (1–2 in mating-disrupted blocks)	https://newa.cornell.edu/crop-and-pest-management & https://extension.unh.edu/resource/fruit-ipm-reports
Oriental Fruit Moth (OFM) Grapholita molesta	First sustained flight / catch (\ge 2 moths caught across consecutive checks)	Base 45^\circ\text{F} BE (Baskerville–Emin single-sine; 90^\circ\text{F} upper cutoff in NEWA)	Gen 1: 1st spray at 150–200\text{ DD}_{45}; 2nd spray at 350–375\text{ DD}_{45} (1st flight subsides \sim 826–1098\text{ DD}). Gen 2: 1150–1200\text{ DD}_{45} & 1450–1500\text{ DD}_{45} (or \sim 250\text{ DD}_{45} after Gen 2 biofix).	Typically >5–10 moths/trap/week (no sprays needed if mating disruption active)	https://newa.cornell.edu/crop-and-pest-management & https://plant-pest-advisory.rutgers.edu/fruit-ipm-updates-week-of-4-27-2026-2/
Obliquebanded Leafroller (OBLR) Choristoneura rosaceana	First sustained flight / catch (\ge 2 moths caught in apple blocks per NYSHS/UMass/NEWA)	Base 43^\circ\text{F} BE (Baskerville–Emin single-sine; 85^\circ\text{F} upper cutoff)	Summer Gen: 5–28% egg hatch and optimal 1st larvicidal spray at 300–360\text{ DD}_{43} post-biofix; scout growing shoots/clusters at 600\text{ DD}_{43} (\sim 1038–1460\text{ DD}_{43} from March 1).	None established for adult traps (UMass 2019); traps set biofix only, action based on 3\% larval cluster infestation	https://newa.cornell.edu/crop-and-pest-management & https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf

Engineering Analysis and Opinion (Resolving the OBLR Biofix Discrepancy in 00_ARGON_BRIEF.md): Section 3 of 00_ARGON_BRIEF.md notes that the OBLR biofix label and the code disagree (uploaded:00_ARGON_BRIEF.md). While a 2013 Michigan State blueberry advisory (https://plant-pest-advisory.rutgers.edu/blueberry-ipm-for-5-22-13/) mentions "first male capture", Cornell's New York Fruit Quarterly (https://nyshs.org/wp-content/uploads/2016/10/Obliquebanded-Leafroller-Management-for-Apple-Production-Investigating-Strategies-for-Resistance-management-with-Emerging-Insecticide-Tools.pdf, "When you start seeing a 'sustained flight', begin the calculation of degree days on your farm or through the NEWA degree day model") and UMass Cold Spring Orchard NEWA reports (https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf, "The 'biofix' date is established when pheromone traps sustain a catch of two or more moths... Oblique-banded leafrollers: sustained catches of OBLR took place ca. 13 June 2019. This is the biofix") confirm that all three Northeast apple pests (CM, OFM, OBLR) use the sustained-catch biofix rule ($\ge 2$ moths) alongside Baskerville–Emin (BE) degree days at bases $50^\circ\text{F}$ (CM), $45^\circ\text{F}$ (OFM), and $43^\circ\text{F}$ (OBLR) (Confidence: Sure).

Grouped Splits by Card and Trap to Avoid Leakage

Measured Results: In arXiv:2609.30278v1 (https://arxiv.org/html/2609.30278v1), within-domain splits yielded $0.884–0.955$ accuracy, whereas strict Leave-One-Site-Out (Region/Trap LOSO) splits revealed true cross-trap generalization of $0.593–0.803$. Similarly, AgriEngineering 2026 (https://www.mdpi.com/2624-7402/8/4/138) demonstrates that applying data augmentation prior to dataset partitioning leaks identical pest textures across train and test sets.

Engineering Analysis and Opinion: Because a single moth stuck on a liner appears in $50\text{ to }150$ consecutive time-lapse photos (uploaded:00_ARGON_BRIEF.md), frame-level or crop-level splitting is completely invalid, and even track-level splitting on the same card leaks card-specific illumination, white balance, and glue state. Therefore, validation must enforce GroupKFold(groups=card_id) (Physical Liner) as the minimum grouping unit, paired with Leave-One-Trap-Out (groups=trap_id) whenever $\ge 2$ traps exist for a class (https://arxiv.org/html/2609.30278v1). Additionally, the team should lock $2$ complete card time-series per pest species ($6$ cards total, $\sim 300–500$ sequential frames) to evaluate end-to-end detect -> track -> classify -> phenology count MAE, daily arrival RMSE, and biofix date error (uploaded:00_ARGON_BRIEF.md, https://zenodo.org/records/22922085).

7. Edge Inference on a Raspberry Pi 5 CPU: Runtimes, Quantisation, and Latency Budget

Hardware Architecture and Benchmark Landscape

Measured Results: The Raspberry Pi 5 Model B features a Broadcom BCM2712 64-bit quad-core ARM Cortex-A76 processor running at $2.4\text{ GHz}$ (up to $2.9\text{ GHz}$ in high-performance mode with active cooling) and $8\text{ GB}$ LPDDR4X RAM, drawing $3.8\text{ W}$ idle and $9.1\text{ W}$ under sustained 4-core CPU inference (https://www.mdpi.com/2504-4990/8/7/204, https://quickfixsurrey.ca/raspberry-pi-5-ai-hat-plus-benchmark/). Peer-reviewed and industrial benchmarks from 2025–2026 establish exact single-image latencies ($640 \times 640$ input unless noted) on the Raspberry Pi 5 CPU across execution runtimes:

Model Architecture	Params / GFLOPs	Runtime & Precision on Raspberry Pi 5 CPU	Measured Latency (ms)	Measured Throughput (FPS)	Quantization Accuracy Impact	Primary Source URL
YOLOv8n	3.01–3.2\text{M} / 8.09–8.7	ONNX Runtime (CPU FP32, 4 cores)	\sim 294.1\text{ ms}	3.40\text{ FPS}	FP32 Reference (36.7\%\text{ mAP})	https://quickfixsurrey.ca/raspberry-pi-5-ai-hat-plus-benchmark/
YOLOv8n	3.01–3.2\text{M} / 8.09–8.7	OpenVINO (ARM CPU IR, 640 \times 640)	\sim 95.2\text{ ms}	10.50\text{ FPS}	No loss (FP16/FP32 IR)	https://www.researchgate.net/publication/393313265_Real-time_small_object_detection_with_YOLOv8n8s_and_YOLOv11n11s_models_in_complex_natural_landscapes
YOLOv8n	3.01–3.2\text{M} / 8.09–8.7	NCNN (CPU FP32, 640 \times 640)	83.7–136.6\text{ ms}	7.32–12.0\text{ FPS}	FP32 Reference (36.7\%\text{ mAP})	https://www.visionanalysis.org/model/yolov8n & https://www.seeedstudio.com/blog/2023/09/28/raspberry-pi-5-vs-pi-4-ai-performance-cpu-benchmark-how-much-leap-forward/
YOLOv11n	2.58\text{M} / 6.31	OpenVINO (ARM CPU IR, 640 \times 640)	\sim 90.6\text{ ms}	11.04\text{ FPS}	+1.96\%\text{ AP@0.5} over YOLOv8n on camera traps	https://www.researchgate.net/publication/393313265_Real-time_small_object_detection_with_YOLOv8n8s_and_YOLOv11n11s_models_in_complex_natural_landscapes
YOLO26n	2.60\text{M} / \sim 6.0	ONNX Runtime INT8 (CPU INT8)	\sim 285.[span_5](start_span)[span_5](end_span)0\text{ ms}	3.51\text{ FPS}	NMS-free; +3.6\text{ mAP} over YOLOv8n	https://www.robolabs.ai/ar/resources/blog/benchmarking-reality-check-cv-model-deployment
MobileNet-SSD	\sim 3.0\text{M} (6.5\text{ MB})	ONNX Runtime INT8 (CPU INT8)	\sim 82.0\text{ ms}	12.20\text{ FPS}	Lower small-object recall than YOLO	https://www.robolabs.ai/ar/resources/blog/benchmarking-reality-check-cv-model-deployment
NanoDet	<1.0\text{M} (<1\text{ MB})	ONNX Runtime INT8 (CPU INT8)	\sim 65.0\text{ ms}	15.38\text{ FPS}	Ultra-fast, lower fine-grained mAP	https://www.robolabs.ai/ar/resources/blog/benchmarking-reality-check-cv-model-deployment
YOLOv8m	25.84\text{M} / 78.69	CPU Baseline (640 \times 640)	>1,500.0\text{ ms}	<0.67\text{ FPS}	Only -0.3\text{ mAP} loss in INT8, but too slow on CPU	https://www.mdpi.com/2079-9292/15/5/1026

Runtime Analysis: ONNX Runtime vs. OpenVINO vs. NCNN vs. INT8 Quantization

Measured Results: Intel's OpenVINO toolkit compiles PyTorch/ONNX models into Intermediate Representation (.xml/.bin) using its ARM Compute Library (ACL) backend, delivering $10.50\text{ FPS}$ ($95.2\text{ ms}$) for YOLOv8n and $11.04\text{ FPS}$ ($90.6\text{ ms}$) for YOLOv11n on the Raspberry Pi 5—nearly $3\times$ faster than default FP32 ONNX Runtime ($3.4\text{ FPS}$ / $294.1\text{ ms}$) (https://www.researchgate.net/publication/393313265_Real-time_small_object_detection_with_YOLOv8n8s_and_YOLOv11n11s_models_in_complex_natural_landscapes, https://quickfixsurrey.ca/raspberry-pi-5-ai-hat-plus-benchmark/). While Tencent's NCNN achieves $83.7\text{ ms}$ ($11.9\text{ FPS}$) on YOLOv8n (https://www.visionanalysis.org/model/yolov8n, a $5\times$ speedup over the Raspberry Pi 4's $414.7\text{ ms}$, https://journals.nupp.edu.ua/sunz/article/download/4689/3984), YOLOv11n contains C3PSA spatial-attention blocks that have triggered segmentation faults in Ultralytics NCNN aarch64 builds on Raspberry Pi 5 (https://community.ultralytics.com/t/raspberry-pi-5-crash-when-running-yolov11n-ncnn/1525). Measured against the FP32 COCO val2017 baseline (https://quickfixsurrey.ca/raspberry-pi-5-ai-hat-plus-benchmark/), post-training INT8 quantization degrades YOLOv8n accuracy by only $0.6\text{ mAP points}$ ($0.4\text{ points}$ for YOLOv8s and $0.3\text{ points}$ for YOLOv8m).

Engineering Analysis and Opinion (End-to-End Pi 5 Server Latency Budget & Open Question #11): On the Raspberry Pi 5 server (server/sentinel_server/), if the background worker runs unquantized PyTorch BioCLIP (ViT-B/16, $86\text{M}$ params) on every insect on a crowded card (e.g., 35 insects $\times 550\text{ ms/crop} \approx 19.3\text{ seconds/photo}$), 4-core CPU saturation will starve FastAPI dashboard requests and trigger SQLite lock timeouts (uploaded:00_ARGON_BRIEF.md). Three optimizations reduce per-photo worker time on the Raspberry Pi 5 from $\sim 15–20\text{ seconds}$ to $< 0.45\text{ seconds}$ (Confidence: Sure):

1. Track-Gated BioCLIP Execution: Associate detected bounding boxes with existing tracks in track.py before calling classify.py. Once a stationary moth's track has accumulated $K = 5$ glare-free BioCLIP embeddings (or human verification), skip BioCLIP inference on all subsequent frames for that track, reducing BioCLIP calls from $20–40$ crops/photo to only the $0–2$ new arrivals per photo.

2. OpenVINO / ONNX INT8 Compilation: Export the 1-class YOLOv8n / YOLOv11n detector to OpenVINO ($\sim 90–95\text{ ms}$ at $640 \times 640$ or $\sim 190\text{ ms}$ at $960 \times 960$, https://www.researchgate.net/publication/393313265_Real-time_small_object_detection_with_YOLOv8n8s_and_YOLOv11n11s_models_in_complex_natural_landscapes) and quantize BioCLIP's ViT-B/16 vision encoder to ONNX Dynamic INT8 / OpenVINO FP16 ($\sim 140\text{ ms/crop}$, $\sim 86\text{ MB}$ RAM).

3. Answering Open Question #11 (BioCLIP + Linear Head vs. Small YOLO Trained on Project Cards): For one season of data where OFM comes from a single trap (uploaded:00_ARGON_BRIEF.md), a two-stage hybrid (1-class YOLOv8n/v11n OpenVINO detector + ArUco Size + BioCLIP Linear Probe classifier) beats both the current OpenCV pipeline and a multi-class YOLO end-to-end classifier (Confidence: Sure). Training a 6-class YOLOv8n to simultaneously localize and classify CM vs. OFM vs. OBLR with only one trap of OFM data guarantees that the YOLO classification head will overfit to that single trap's background (https://arxiv.org/html/2609.30278v1). Using YOLOv8n/YOLOv11n strictly as a class-agnostic insect box detector while keeping the frozen BioCLIP + Calibrated Size ($\text{mm}$) Linear Probe for species ID combines YOLO's $>92\%$ localization recall with BioCLIP's 10M-image taxonomic prior (https://pmc.ncbi.nlm.nih.gov/articles/PMC11922902/, https://arxiv.org/abs/2311.18803).

8. Ranked Pipeline Recommendations and Actionable Codebase Changes

Summary Ranking by Expected Accuracy Gain per Hour of Student Work

To maximize field reliability within a single academic season (uploaded:00_ARGON_BRIEF.md), the eight recommended modifications are ranked below by expected accuracy/reliability gain per hour of student engineering effort:

Priority Rank	Finding ID & Upgrade Title	Target Module / File	Effort Tier & Student Hours	Expected Accuracy / Reliability Gain	ROI Score (Gain / Hour)	Confidence
Rank 1	CV-01: Clamp grid scale to hardware constant (15.3\text{ px/mm}) & remove first-photo lock	server/sentinel_server/pipeline/detect.py	S (2\text{ hrs})	+25.0\text{ pts} on affected cards (fixes 50\% scale failure)	12.5\text{ pts/hr}	Sure
Rank 2	SRV-01: Gate sustained-catch biofix on human review & align OBLR to Base 43^\circ\text{F} BE	server/sentinel_server/pipeline/phenology.py & services.py	S (3\text{ hrs})	+15.0\text{ pts} biofix decision reliability (\pm 1\text{ day} target)	5.0\text{ pts/hr}	Sure
Rank 3	ML-01: Append calibrated physical size (\text{mm}) & lure prior to BioCLIP linear probe	server/sentinel_server/pipeline/classify.py & ml/train_v1.py	S (4\text{ hrs})	+18.0\text{ pts} on CM vs. OFM separation on glue	4.5\text{ pts/hr}	Sure
Rank 4	HW-01: Add \$0.50 cross-polarizer films on LED & lens + HLS glare mask + header AWB	hardware/scad/camera_mount.scad & detect.py	S (3\text{ hrs})	+12.0\text{ pts} (eliminates 10–13\% glare blowout)	4.0\text{ pts/hr}	Sure
Rank 5	CV-02: Freeze track species consensus on first 5 fresh frames & detect liner swaps	server/sentinel_server/pipeline/track.py & worker.py	S (5\text{ hrs})	+11.0\text{ pts} long-card ID stability + 10\times faster worker	2.2\text{ pts/hr}	Sure
Rank 6	ML-02: Cure OFM single-trap shortcut via Poisson background swap & Outlier Exposure	ml/train_v1.py & dataset prep scripts	M (12\text{ hrs})	+18.0\text{ pt[span_6](start_span)[span_6](end_span)s} cross-trap LOSO & other_moth OOD rejection	1.5\text{ pts/hr}	Sure
Rank 7	CV-03: Replace OpenCV detector with 1-class YOLOv8n OpenVINO + INT8 BioCLIP	server/sentinel_server/pipeline/detect.py & classify.py	M (16\[span_7](start_span)[span_7](end_span)text{ hrs})	+20.0\text{ pts} localization recall on grid lines (<0.45\text{ s/img})	1.25\text{ pts/hr}	Sure
Rank 8	HW-02: Print 188\text{ mm} ArUco slide-in liner tray & upgrade to full-card OV5640 (5\text{ MP})	hardware/scad/liner_tray.scad & detect.py	M (24\text{ hrs})	+24.0\text{ pts} whole-card catch coverage (28.4\% \to 100\%)	1.0\text{ pts/hr}	Sure

Detailed Specifications of Ranked Findings (Section 4 Brief Format)

CV-01 · Clamp grid scale to hardware constant (15.3 px/mm) and remove first-photo scale lock

⚬ Severity: critical | Confidence: Sure | Effort: S (2 hours)

⚬ Where: server/sentinel_server/pipeline/detect.py (grid scale estimation and card scale persistence)

⚬ Evidence: "the grid finder misreads photos with insects on them (5 of 10 read 32–63 px/mm instead of 15.3); the scale check trusts a liner's first photos." (uploaded:00_ARGON_BRIEF.md, Section 3)

⚬ What goes wrong: When moths or specular glare land on the $25\text{ mm}$ printed grid lines, the spatial period estimator locks onto $2\times–4\times$ spatial harmonics ($32–63\text{ px/mm}$). Because the scale validation logic locks in a liner's initial reading, all subsequent insect crops on that card have their physical dimensions underestimated by $2\times–4\times$, causing $10\text{ mm}$ CM and OBLR moths to be measured as $2.5–5.0\text{ mm}$ (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf).

⚬ Fix: Because camera-to-floor geometry is physically fixed ($110\text{ mm}$), enforce a sanity clamp around the calibrated optical constant ($15.3\text{ px/mm}$ for OV3660; $14.8\text{ px/mm}$ for full-card OV5640) and fall back to the nominal constant whenever the grid finder diverges:

[python]
NOMINAL_PX_PER_MM = 15.3
MIN_VALID_SCALE, MAX_VALID_SCALE = 13.8, 16.8
if not (MIN_VALID_SCALE <= measured_px_per_mm <= MAX_VALID_SCALE):
    measured_px_per_mm = NOMINAL_PX_PER_MM


SRV-01 · Gate sustained-catch biofix on human review and align OBLR to NEWA Base 43°F BE sustained catch

⚬ Severity: critical | Confidence: Sure | Effort: S (3 hours)

⚬ Where: server/sentinel_server/pipeline/phenology.py and server/sentinel_server/services.py, phenology_status()

⚬ Evidence: "Getting the biofix date right, to within a day, matters more than counting every moth perfectly." / "the OBLR biofix label and the code disagree" (uploaded:00_ARGON_BRIEF.md, Sections 1 & 3)

⚬ What goes wrong: A single unreviewed false positive on an early spring card can prematurely trigger the sustained-catch biofix, shifting cumulative degree days by $10–30\text{ days}$ (https://www.canr.msu.edu/news/dont-trust-the-calendar-why-trapping-matters-during-unusual-weather). Additionally, OBLR in Northeast apple IPM uses sustained flight ($\ge 2$ moths) with Base $43^\circ\text{F}$ Baskerville–Emin degree days (https://newa.cornell.edu/crop-and-pest-management, https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf).

⚬ Fix: Standardize all three pests in phenology.py to NEWA's Baskerville–Emin (BE) degree-day calculation with bases CM = $50^\circ\text{F}$, OFM = $45^\circ\text{F}$, and OBLR = $43^\circ\text{F}$ and a sustained-catch biofix ($\ge 2$ moths). Before locking a block's biofix for the season, require that any track contributing to the biofix trigger has either review_status == "approved" or confidence >= 0.92 (where https://arxiv.org/html/2609.30278v1 proves the error rate is $1.15\%$), routing lower-confidence pre-biofix catches to the top of the review queue.

ML-01 · Concatenate calibrated physical size features (mm) and lure prior to BioCLIP linear probe

⚬ Severity: critical | Confidence: Sure | Effort: S (4 hours)

⚬ Where: server/sentinel_server/pipeline/classify.py and ml/train_v1.py

⚬ Evidence: "classify (BioCLIP embeddings + linear head, or a trained checkpoint)" (uploaded:00_ARGON_BRIEF.md, Section 2)

⚬ What goes wrong: BioCLIP's ViT-B/16 preprocessor (https://huggingface.co/imageomics/bioclip/blob/refs%2Fpr%2F11/README.md) resizes every bounding-box crop to $224 \times 224\text{ pixels}$, erasing absolute physical size. On sticky glue, where polybutene wicking darkens wing scales into uniform black/brown (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf), the $2–4\text{ mm}$ body-length gap between OFM ($4.5–7.0\text{ mm}$) and CM/OBLR ($7.6–12.0\text{ mm}$) is the primary separator.

⚬ Fix: Compute standardized physical morphology features from the scale-corrected bounding box and contour (https://www.biorxiv.org/content/10.1101/2023.12.05.570242v2.full-text) and concatenate them with the L2-normalized 512-D BioCLIP image embedding before fitting the L2-regularized LogisticRegression head, coupled with a lure-consistency confidence gate:

[python]
morph_vec = np.array([length_mm, width_mm, np.sqrt(area_mm2), aspect_ratio, solidity])
morph_norm = (morph_vec - morph_mean) / (morph_std + 1e-6)
features_517d = np.concatenate([bioclip_emb_512d, morph_norm])


HW-01 · Install orthogonal linear polarizer films on LED and camera lens + software HLS glare mask

⚬ Severity: high | Confidence: Sure | Effort: S (3 hours)

⚬ Where: hardware/scad/camera_mount.scad and server/sentinel_server/pipeline/detect.py

⚬ Evidence: "Lighting: an LED lights the card. 10–13 % of the card is blown out by glare, and there's no diffuser yet." (uploaded:00_ARGON_BRIEF.md, Section 2)

⚬ What goes wrong: Specular reflection off the flat glossy glue saturates $10–13\%$ of pixels to white, generating false-positive blob detections and washing out CM's coppery apical wing patch (https://fjwoptical.com/blogs/blog/lighting-the-role-of-polarized-lighting-in-reducing-glare-and-reflections).

⚬ Fix: Adhere a $0^\circ$ linear polarizing film plus a thin matte diffuser over the white LED and a $90^\circ$ orthogonal linear polarizing film over the camera lens ($<\$0.50\text{/trap}$, https://docs.sharktacos.com/photography/xpol.html). In detect.py, compute glare_mask = (L > 240) & (S < 30) in HLS space to suppress glare blobs on legacy unpolarized photos, and normalize card white balance using the 90th-percentile RGB of the $174 \times 22\text{ mm}$ white printed header (https://academic.oup.com/aesa/article/99/5/865/12163).

CV-02 · Freeze track species consensus on first 5 fresh frames and detect unannounced liner swaps

⚬ Severity: high | Confidence: Sure | Effort: S (5 hours)

⚬ Where: server/sentinel_server/pipeline/track.py and server/sentinel_server/pipeline/worker.py

⚬ Evidence: "track each insect across the liner's photos so each is counted once -> classify -> species consensus per track" / "someone changing a liner without pressing the bu[span_319](start_span)[span_319](end_span)[span_321](start_span)[span_321](end_span)tton" (uploaded:00_ARGON_BRIEF.md, Sections 2 & C2)

⚬ What goes wrong: Over $1–4\text{ weeks}$, glue wicking turns moths solid black (https://idtools.org/id/leps/tortai/Thaumatotibia%20leucotreta_LoRes.pdf) and wasps/ants scavenge carcasses (https://open-research-europe.ec.europa.eu/articles/6-421), so late frames degrade early classifications while re-running BioCLIP on all stationary moths wastes $\sim 15\text{ seconds}$ of Pi 5 CPU time per upload. Additionally, newly caught moths struggle and shift position during their first $24\text{ hours}$ (https://www.researchgate.net/figure/A-Three-consecutive-photographs-taken-by-the-IR-camera-the-fi-rst-two-were-taken-before_fig3_355318381), and unannounced liner swaps corrupt track histories.

⚬ Fix: Use a two-tier Hungarian matching radius in track.py: $18.0\text{ mm}$ (gated by BioCLIP cosine similarity $>0.80$) for tracks $<24\text{ hours}$ old, tightening to $3.5\text{ mm}$ for tracks $>24\text{ hours}$ old. Once a track accumulates $K = 5$ glare-free crops (or is human-reviewed), freeze its species_consensus and skip BioCLIP inference on subsequent frames. If a card has $\ge 2$ established tracks (age $\ge 3$ frames) and $\ge 80\%$ vanish across two consecutive valid frames, automatically emit a new_liner_detected event and archive prior tracks (https://legacy.trapview.com/trapview_help/html/device_events.html).

ML-02 · Cure OFM single-trap shortcut via foreground background-swapping and Open-Insects Outlier Exposure

⚬ Severity: high | Confidence: Sure | Effort: M (12 hours)

⚬ Where: ml/train_v1.py and dataset preparation scripts

⚬ Evidence: "a second OFM data source (every model learnt one trap's look)" (uploade[span_287](start_span)[span_287](end_span)d:00_ARGON_BRIEF.md, Section 3)

⚬ What goes wrong: Because all OFM crops come from a single trap, the classifier learns background glue/lighting shortcuts rather than moth morphology, causing severe accuracy drops on new traps (https://arxiv.org/html/2609.30278v1). Simultaneously, unseen local tortricids (other_moth) are misclassified as target pests with high softmax probability (https://arxiv.org/html/2503.01691v1).

⚬ Fix: Segment each training moth from its local liner patch via Otsu thresholding and Poisson-blend (cv2.seamlessClone) the moth foreground onto random empty background patches cropped from all other traps' liners (https://spiral.imperial.ac.uk/server/api/core/bitstreams/afebbaa6-026a-48f2-94aa-89314b8ea80f/content). Augment the other_moth training class with $500–1,000$ Northeastern North America tortricid crops from Open-Insects (https://huggingface.co/datasets/yuyan-chen/open-insect) and AMI-Traps (https://zenodo.org/records/11358689) as Outlier Exposure, and evaluate strictly via GroupKFold(groups=card_id) and Leave-One-Trap-Out splits.

CV-03 · Replace OpenCV blob/grid detector with 1-class YOLOv8n/YOLOv11n in OpenVINO and quantize BioCLIP

⚬ Severity: high | Confidence: Sure | Effort: M (16 hours)

⚬ Where: server/sentinel_server/pipeline/detect.py and server/sentinel_server/pipeline/classify.py

⚬ Evidence: "detect (OpenCV baseline that measures the liner's 25 mm grid for scale and removes grid lines)" / "Server is a Raspberry Pi 5 (no GPU)" (uploaded:00_ARGON_BRIEF.md, Sections 1 & 2)

⚬ What goes wrong: Classical OpenCV blob detection fails on grid intersections, touching moths, and uneven shadows, while unquantized PyTorch inference on the Pi 5 CPU is slow (https://www.mdpi.com/2071-1050/14/15/9729, https://quickfixsurrey.ca/raspberry-pi-5-ai-hat-plus-benchmark/).

⚬ Fix: Train a 1-class (insect) YOLOv8n or YOLOv11n detector using the team's labeled cards, Poisson-blended Copy-Paste moths, and public sticky-card datasets (Zenodo 139300[span_209](start_span)[span_209](end_span)[span_213](start_span)[span_213](end_span)55 Flat Bug and Zenodo 7801239 PST). Export to OpenVINO FP16/INT8 ($90.6–95.2\text{ ms}$ per frame on Pi 5 CPU, https://www.researchgate.net/publication/393313265_Real-time_s[span_231](start_span)[span_231](end_span)mall_object_detection_with_YOLOv8n8s_and_YOLOv11n11s_models_in_complex_natural_landscapes) with IoA-SoftNMS (https://www.preprints.org/manuscript/202609.1035/v1) at imgsz=960 without SAHI tiling, and export BioCLIP's image encoder to ONNX INT8 / OpenVINO ($\sim 140\text{ ms/crop}$).

HW-02 · Print narrow 188 mm ArUco slide-in liner tray and upgrade to full-card OV5640 (5 MP)

⚬ Severity: medium | Confidence: Sure | Effort: M (24 hours)

⚬ Where: hardware/scad/liner_tray.scad, hardware/scad/camera_mount.scad, and server/sentinel_server/pipeline/detect.py

⚬ Evidence: "Its OV3660 (3 MP) lens is narrow (~66°): from 110 mm it sees only ~115 × 85 mm of the card. Plan: an OV5640 (5 MP) with a wider lens." / "liner_tray.scad, a slide-in liner tray with ArUco corner markers. It's wider than the floor and needs a redesign." (uploaded:00_ARGON_BRIEF.md, Section 2)

⚬ What goes wrong: The narrow OV3660 misses $71.6\%$ of the $174 \times 198\text{ mm}$ liner, causing multi-day delays in detecting first sustained flight at low pest densities (https://open-research-europe.ec.europa.eu/articles/6-421).

⚬ Fix: Narrow liner_tray.scad to $188\text{ mm}$ outer width so it slides cleanly inside the $195\text{ mm}$ floor, placing four $15 \times 15\text{ mm}$ DICT_4X4_[span_8](start_span)[span_8](end_span)50 ArUco markers on raised corner tabs outside the glue zone. In detect.py, use cv2.aruco.ArucoDetector to compute the 4-corner homography and warp every photo to a canonical $15.0\text{ px/mm}$ top-down plane. Upgrade the node camera to an OV5640 ($5\text{ MP}$, $2592 \times 1944$) with an $\sim 85^\circ–90^\circ$ lens calibrated with a static cv2.initUndistortRectifyMap lookup table, achieving $\sim 14.8\text{ px/mm}$ across $100\%$ of the active $174 \times 175\text{ mm}$ sticky grid (https://preprints.arphahub.com/article/214480/download/pdf/).




Sources used in the report
  Fruit IPM Reports - UNH Extension

  Mothbox: inexpensive, lightweight, automated light trap for scalable

  Mothbox: inexpensive, lightweight, automated light trap for scalable

  (PDF) Species-level image classification with convolutional neural

  Analysis of Insect and Plant Colors in Digital Images Using Java

  Results of dataset construction: Three datasets regarding the

  SatoyamaCT: A Multi-Axis Night-IR Camera-Trap Benchmark ... - arXiv

  Morphological OTUs reshape our understanding of Earth's life

  MorphOTU: image-derived morphological operational units for open

  BIOANALYST:AFOUNDATION MODEL FOR BIODIVERSITY

  BIOSCAN-5M: A Multimodal Dataset for Insect Biodiversity - arXiv

  (PDF) BIOSCAN-5M: A Multimodal Dataset for Insect Biodiversity

  BIOSCAN-5M: A Multimodal Dataset for Insect Biodiversity - NIPS

  Codling Moths: ID, Apple Damage & Control - Better Termite

  Grapholita inopinata, G. packardi and G. prunivora - ArcGIS StoryMaps

  Grapholita prunivora (plum moth) | CABI Compendium

  Grapholita funebrana - Cooperative Agricultural Pest Survey

  Screening Aid - IDtools

  The reared codling moth, Cydia pomonella in the laboratory. (a

  Species-Specific COI Primers for Rapid Molecular Identification of

  Choristoneura rosaceana - Wikipedia

  About Oblique-banded Leafroller Moth - Maryland Biodiversity Project

  Choristoneura rosaceana (oblique banded leaf roller)

  Obliquebanded Leafroller (Choristoneura rosaceana) - Cornell CALS

  Maple Feeding Tortricidae of the Northeastern United States

  Pest Sticky Traps: a dataset for Whitefly Pest Population Density

  Pest Sticky Traps: a dataset for Whitefly Pest Population Density

  Persistent monitoring of insect-pests on sticky traps through

  Persistent monitoring of insect-pests on sticky traps through ... - PMC

  insect-trap-webpage - Gvtone - GitHub

  YOLO26-USW: A Slice-Aided Semantic–Detail Fusion Detector for

  Insect Detection and Identification using YOLO Algorithms on

  Detecting insect pests on sticky traps based on improved YOLOv11n

  Slicing-Aided Hyper Inference for Small-Insect Detection and

  Improved YOLOv8 and SAHI Model for the Collaborative Detection

  A Performance Analysis of You Only Look Once Models for ... - arXiv

  Raspberry Pi 5 vs. Pi 4 AI performance CPU Benchmark

  Raspberry Pi 5 Crash When Running YOLOv11n NCNN - YOLO

  Low Cost Machine Vision for Insect Classification - arXiv

  (PDF) Pest-PVT: A model for multi-class and dense pest detection

  YOLO-LCE: A Lightweight YOLOv8 Model for Agricultural Pest

  Pest-YOLO: A model for large-scale multi-class dense and tiny pest

  INS_2 | Meta Album

  IP102-Dataset - Kaggle

  IP102: A Large-Scale Benchmark Dataset for Insect Pest Recognition

  IP102: A Large-Scale Benchmark Dataset for Insect Pest Recognition

  Insect Identification in the Wild: The AMI Dataset - Zenodo

  RolnickLab repositories · GitHub

  Deep learning―based automatic counting of thrips captured on

  Identifying common stored product insects using automated deep

  Whole-drawer imaging for digital management and curation of a

  LEPMON: Recording the biodiversity of moths (Lepidoptera) with

  Species‐level image classification with convolutional neural network

  Detecting Thrips and Larger Insects Together - Wildlabs

  Tracking individual honeybees among wildflower clusters with

  An annotated image dataset of pests on different coloured sticky

  Sticky Pi, an AI-powered smart insect trap for community ... - bioRxiv

  Sticky Pi is a high-frequency smart trap that enables the study of

  A novel dataset and deep learning object detection benchmark for

  Applying Polarization-Based Traps to Insect Control - ResearchGate

  Research on a Macro-Scale Pest Detection Algorithm Based on an

  SP-YOLO: A Real-Time and Efficient Multi-Scale Model for Pest

  Research on Rice Pest Detection and Classification Based ... - MDPI

  PestFG-RTDETR: An Efficient Pest Detector for Small Targets in

  Multiple Kernel Attention Network for Dense and Tiny Wheat Pest

  Synthetic dataset for object detection in the agriculture domain - Spiral

  GAN-based semi-automated augmentation online tool for ... - PMC

  Insect Detect: An open-source DIY camera trap for automated insect

  Methods of insect image capture and classification

  A novel dataset and deep learning object detection benchmark for

  A Case Study on Pest and Disease Detection in Precision Viticulture

  Insect Identification in the Wild: The AMI Dataset - arXiv

  Using Deep Learning for Detection and Classification of Insects on

  A Comprehensive Evaluation of YOLO-based Deer Detection ... - arXiv

  Real-time small object detection with YOLOv8n/8s and YOLOv11n

  Raspberry Pi 5 AI HAT+ Benchmark: Real YOLOv8 FPS Tested

  A Comprehensive Evaluation of YOLO-Based Deer Detection

  What the Numbers Really Mean for Your Computer Vision Deployment

  yolo family architectures for explosive object detection in embedded

  YOLOv8-N Benchmark Results - Vision Analysis

  Benchmarking YOLOv8–YOLOv12 for Real-Time Object Detection

  [2311.18803] BioCLIP: A Vision Foundation Model for the Tree of Life

  BioCLIP: A Vision Foundation Model for the Tree of Life - arXiv

  README.md · imageomics/bioclip at refs/pr/11 - Hugging Face

  BioCLIP: A Vision Foundation Model for the Tree of Life - alphaXiv

  Cross Polarization: What It Is and Why It Matters | PetaPixel

  Cross-Polarization Photography | Glare Reduction | XangleCS

  Cross-Polarization Photography for Textures - Light Collab

  Lighting: The Role of Polarized Lighting in Reducing Glare and Reflect

  Cross-Polarized Macro: Kill Specular Glare Cleanly - Venus Optics

  Glare Reduction and Polarizers - Online Solutions

  PeMaToEuroPep - Zenodo

  2-class Grapevine Pest Dataset of Scaphoideus titanus and Orientus

  Image Dataset of Brown Marmorated Stink Bug (BMSB) or ... - Zenodo

  Resolution, Cadence and Decision Error in Automated Sticky-Trap

  Support Vector Machine (SVM) Recognition Approach adapted to

  Field detection of tiny pests from sticky trap images using deep

  Plum Curculio Waining, Codling Moth Waxing. Residual for PC

  The resurgence of Codling Moth in the Hudson Valley

  Fruit IPM Report 5/11/2026 - Plant & Pest Advisory

  Scaffolds Podcast Digest: Season 4, Episode 17 (July 21 2026

  Fruit IPM Report June 17, 2025 - Plant & Pest Advisory

  Integrated Pest Management Crop Production Tools | NEWA

  Healthy Fruit, Vol. 27, No. 12, June 25, 2019

  Don't trust the calendar: Why trapping matters during unusual weather

  Blueberry IPM for 5-22-13 - Plant & Pest Advisory

  Obliquebanded Leafroller Management for Apple Production

  2026-2027 intermountain tree fruit production guide

  Keeping the Reins on Codling Moth » The Jentsch Lab - Cornell blogs

  Large testing of AI-based camera traps on... | Open Research Europe

  Device events — trapview 4.47 documentation

  Dr. Steve Sheppard

  Research on a machine vision-based electro-killing pheromone

  A -Three consecutive photographs taken by the IR camera, the fi rst

  EyesOnTraps: AI-Powered Mobile-Based Solution for Pest ... - MDPI

  yuyan-chen/open-insect · Datasets at Hugging Face

  Open-Insect: Benchmarking Open-Set Recognition of Novel Species

  Open-Set Recognition of Novel Species in Biodiversity Monitoring

  Support-Derived Multi-Prototypes for Hierarchical Few-Shot Open

  GinJinn2 - yellow-sticky-traps dataset

  ‪Ard Nieuwenhuizen - ‪Google Scholar

  Novel Tool for Complete Digitization of Paper Electrocardiography

  SlidePrep removes chamber grids and reconstructs whole-slide

  [Solved] Extract Data From Line Graph Image via Python




Sources read but not used
  CIPRA Computer Centre for Agricultural Pest Forecasting

  Improved insect control strategies utilizing pheromones and rnai

  Orchard plant protection guide for deciduous fruits in NSW 2026–27

  Orchard Pest Management - Amazon S3

  The Hidden Company That Trees Keep: Life from Treetops to Root

  PLANT PROTECTION 1

  Suction Flows Generated by the Carnivorous Bladderwort Utricularia

  Using Spatial Structure Analysis of Hyperspectral Imaging Data and

  Daily Papers - Hugging Face

  Faunari/docs/TECHNICAL_DEEP_DIVE.md at master · dhruv7477

  Book The - Trécé

  Grapholita funebrana - Cooperative Agricultural Pest Survey

  Oriental fruit moth

  Tortricidae - Plazi TreatmentBank

  Blueberry Export to Korea

  10 Types of Tortrix Moths: Id with Pictures, Habitat & Lifecycle

  LBAM Screening & Identification.indd - IDtools

  Obliquebanded leafroller - Ontario Crop IPM - Raspberries

  URBANE - WP5 - Database for pest detection using smart ... - Zenodo

  Large testing of AI-based camera traps on a forest defoliating pest in

  Raw data from Yellow Sticky Traps with insects for training of deep

  High-Precision Detection of Homona magnanima and Adoxophyes

  Quantifying the Frontal-to-Ceiling Domain Gap for YOLO-Based

  A deep learning based system for real-time ... - Semantic Scholar

  CMC | A Review on the Application of Deep Learning Methods in

  A Lightweight Crop Pest Detection Algorithm Based on Improved

  Enhancing Insect Species Classification through Multi-Level Feature

  EP-YOLO: An Enhanced Lightweight Model for Micro-Pest Detection

  IBBI-bio/ibbi_yolo11x_arthropod_detector · Hugging Face

  adhiiisetiawan/large-scale-pest-recognition - GitHub

  IP102: A large-scale benchmark dataset for insect pest recognition

  IP102: A Large-Scale Benchmark Dataset for Insect Pest Recognition

  Official code of the paper "Deep-Wide Learning Assistance for Insect

  PROB-IP102-custom/ip102_prob_training.ipynb at main - GitHub

  Awesome Analysis Tools Awesome - InsectAI-COST-Action - GitHub

  Internet of Things Meets Computer Vision to Make an Intelligent Pest

  Abstract - arXiv

  Digital-Naturalism-Laboratories/Automated-Insect-Monitoring

  (PDF) Image-based automated identification of SBR-transmitting

  The first flat wasps (Hymenoptera: Bethylidae) from Miocene

  (PDF) Correlation of the Middle Miocene deposits in SE Poland and

  entomological field techniques: Topics by Science.gov

  14th Czech - Slovak – Polish Palaeontological Conference

  ghats southern india: Topics by Science.gov

  Soil Organic Matter Characteristics as Affected by Tillage Management

  Real-Time Forestry Pest Detection Method ... - Semantic Scholar

  Ghiasi, G., Cui, Y., Srinivas, A., Qian, R., Lin, T. Y., Cubuk ... - SCIRP

  Methods of Insect Image Capture and Classification: A Systematic

  Edge Object Detection Models Guide - Digital Fractal Technologies Inc

  wikan1602/ada-mata-mle-test: Real-time bottle cap ... - GitHub

  Benchmarking YOLOv8–YOLOv12 for Real-Time Object Detection

  inference Archives - Latest News from Seeed Studio

  BioCLIP: A Vision Foundation Model for the Tree of Life - OpenTrain AI

  BioCLIP: A Vision Foundation Model for the Tree of Life - OpenReview

  BioCLIP, a Vision Foundation Model for Biology (r/MachineLearning)

  Li Dong - Microsoft Research

  BioCLIP 2 - Zenodo

  initial model card update · imageomics/bioclip at 74129d1

  Cross Polarization Tutorial: Removing Specular Highlights and

  Cross-polarization demo - the last word - Jim Kasson

  Using Multiple Natural Enemies to Manage Sweetpotato Whiteflies

  (PDF) An image dataset of fruitfly species (Bactrocera Zonata and

  Conspecific cueing or cooperative feeding?

  Submissões - Entomology Beginners

  (PDF) Revolutionizing tomato pest management: Synergy of Deep

  Classification Jobs, Employment - Freelancer

  EntomoBrasilis publication guidelines v6.1 (February 2024)

  Faculty of Agriculture - Patuakhali Science and Technology University

  Behavioral responses of predatory flies of the genus Medetera

  100 days of code: ai for agriculture - tassiane anzolin

  Dataset and Weights for "An operational workflow for automated

  pinoy2023 | Zenodo

  May 30, AppleTalk Conference Call - IPM Institute

  NYSHSociety - New York State Horticultural Society

  Healthy Fruit, Vol. 24, No. 5, April 26, 2016

  proceedings - Cumberland-Shenandoah Fruit Workers Conference

  Nielsen – Codling Moth Management

  NEWA (Network for Environment and Weather Applications

  HEALTHY FRUIT Vol. 21, No. 8, May 21, 2013

  New Hampshire IPM Newsletter - UNH Extension

  Healthy Fruit, Vol. 23, No. 9, June 2, 2015

  NEWA Report to NYS IPM Program - Results Verification System

  Evaluating the Effect of Mating Disruption and Parasitoids on

  AI-Powered Mobile Image Acquisition of Vineyard ... - Researcher.Life

  Field Comparison of Manual and Automated Trapping Systems for

  Open-Set Recognition of Novel Species in Biodiversity Monitoring

  Class-conditioned Unknown Boundary Evidence for Open-Set Insect

  #23 PATS - 4TU.Federatie

  Loss of olfaction reduces caterpillar performance and increases

  (PDF) Sweep netting samples, but not sticky trap ... - ResearchGate

  Wageningen Model & Data Day 2024 - Sessions

  Loss of olfaction reduces caterpillar performance and increases

  Quantifying the spatial scales of animal clusters using density surfaces

  Loss of olfaction reduces caterpillar performance and increases

  Elimination of gridlines in X-ray image - ResearchGate

  A method for removing filter line patterns from X-ray images

  Hybrid Deep Learning Based Model for Removing Grid-Line

  Antiscatter Grids: Scatter, Contrast & Dose - Diagnostic Radiation




Thoughts
