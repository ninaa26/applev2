End-to-End Architecture, Field Hardware, and Pipeline Design for Automated Insect-Trap Camera Systems

1. Commercial Automated Pest Monitoring Systems

Commercial automated insect monitoring platforms have evolved along two distinct technological trajectories: periodic optical sticky-trap imaging systems (represented by Trapview, Pessl Instruments iSCOUT, Semios, CropVue, and xFarm) and continuous non-imaging event sensors that measure bio-impedance or optical wingbeat modulation (represented by the DTN/Spensa Z-Trap and FarmSense FlightSensor) (https://metos.global/en/iscout/, https://www.researchgate.net/publication/388811374_New_tools_to_monitor_Scaphoideus_titanus_the_main_vector_of_phytoplasmas_associated_with_Flavescence_doree_in_vineyards, https://biologicalag.com.au/products/cropvue-automated-delta-traps, https://farmsense.io/about-us, https://www.globalagtechinitiative.com/in-field-technologies/connectivity/technology-takes-field-scouting-to-the-next-level/). A third category frequently cited in agricultural instrumentation literature—represented by Ecomatik—does not manufacture insect camera traps at all, but rather produces high-precision plant physiological sensors (such as the DC3 and DD-L stem dendrometers with $0.2\ \mu\text{m}$ resolution and $\pm 0.1\%$ accuracy, alongside leaf turgor sensors) that are paired with third-party camera or environmental loggers in integrated orchard studies (https://pmc.ncbi.nlm.nih.gov/articles/PMC11608269/, https://r-libre.teluq.ca/3376/1/978-3-030-80767-2_16.pdf, https://orbi.uliege.be/bitstream/2268/329626/1/Basile%20LUSE%20BELANGANAYI%20-%20Thesis%20Dissertation.pdf). In Chinese and Asian distribution catalogs (such as DianJiang Group), Ecomatik plant sensors are co-listed alongside standalone wildlife infrared camera traps like the DJ-075X series ($5\text{--}32\text{ MP}$, PIR-triggered, $4\text{G}$, IP68) and Termatrac radar pest sensors, which frequently causes confusion in broad literature surveys (https://www.dianjianghk.com/product/showproduct.php?lang=en&id=1827, https://www.dianjianghk.com/product/showproduct.php?lang=en&id=1604).

Empirical Comparison of Commercial Platforms

The following table synthesizes the verified hardware, communication, inference, and pricing specifications across commercial systems (https://metos.global/en/iscout/, https://trapview.com/, https://www.semios.com/solutions/insect-pest-management/, https://farmsense.io/about-us, https://biologicalag.com.au/products/cropvue-automated-delta-traps).

System & Vendor	Capture Frequency & Resolution	Lighting & Trap Geometry	Power Architecture & Battery Life	Connectivity & Transfer	Inference Location & Counting Logic	Reported Accuracy & Validation	Human Review & Correction	Pricing Model
Trapview (EFOS d.o.o., Slovenia)	Programmable; typically 1\text{--}3 photos/day (usually midday). 8 MP camera (earlier versions used 4x5 MP array or 5 MP) (https://www.researchgate.net/publication/388811374_New_tools_to_monitor_Scaphoideus_titanus_the_main_vector_of_phytoplasmas_associated_with_Flavescence_doree_in_vineyards).	White LED flash illumination inside enclosed delta, vertical self-cleaning (SCM), or UV light (Aura) housing (80 \times 45 \times 22\text{ cm} for Vertical SCM).	3.6\text{ V}, 6.7\text{ Ah} Li-ion battery charged by a 3\text{ W} (13 \times 18\text{ cm}) solar panel; lasts full season autonomously.	Direct cellular (4\text{G} / LTE / GPRS internal modem) with onboard GPS receiver.	Cloud inference. Tracks insect bounding boxes across daily images or advances adhesive roll via motorized self-cleaning mechanism (SCM) to expose clean glue.	Vendor claims high accuracy across 60+ species and 30M+ images; independent field trial by Preti et al. (2021) found low automatic-to-manual correlation when non-targets were present (https://www.researchgate.net/publication/351210617_Remote_monitoring_of_Cydia_pomonella_adults_among_an_assemblage_of_nontargets_in_sex_pheromone-kairomone-baited_smart_traps).	Mandatory/standard human-in-the-loop verification by vendor specialists within \le 24\text{ h}; users can also review and adjust markers in web app (https://trapview.com/).	Subscription service package: approx. \$1,375/\text{ha} per year (https://www.mdpi.com/2075-1702/10/1/52).
METOS iSCOUT (Pessl Instruments, Austria)	User-selectable: 1 photo/day on GPRS or up to 3 photos/day on LTE. 10 MP camera (https://metos.global/en/iscout/).	Ambient daylight diffused through white/translucent trap housing or open color-plate holder; housing is 20 \times 15.5 \times 17\text{ cm}, weight 0.93\text{ kg}.	Rechargeable 6\text{ V}, 12\text{ Ah} lead-acid/battery (-35^\circ\text{C} to 80^\circ\text{C} range) + 7.2\text{ V}, 333\text{ mA} (2.4\text{ W}, 17.5 \times 17.5\text{ cm}) solar panel.	Cellular LTE Class 1 or GPRS modem; transmits every 60\text{ min} after photo capture; 32 MB RAM + 8 GB local photo storage.	Cloud inference on FieldClimate portal. Tracks persistent bounding boxes across sequential images of the sticky plate.	Evaluated in European H2020 SmartProtect trials (https://platform.smartprotect-h2020.eu/en/view/ipm/16); high detection on low-density plates, degrades under overlapping saturation.	Users view annotated high-resolution photos on the FieldClimate web portal and can manually relabel or correct bounding boxes (https://metos.global/en/iscout/).	Purchase: €1,040 (Pheromone) or €1,130 (Color Trap) including portal; Rental: ~€300/season (https://platform.smartprotect-h2020.eu/en/view/ipm/16).
Semios Automated Camera Trap (Semios, Canada)	1 photo/day (standard daily report). High-resolution RGB camera inside delta/box housing (https://www.semios.com/solutions/insect-pest-management/).	Internal LED flash triggered during image capture inside a weather-resistant plastic delta body.	Rechargeable lithium battery pack with external solar panel unit mounted on canopy pole; full-season operation.	Proprietary sub-GHz / ISM mesh network from traps to a central farm gateway, which backhauls via cellular.	Cloud inference paired with internal human QA team. Counts new arrivals by comparing daily images against prior day's sticky liner state.	Field-validated across Washington, California, and BC orchards for CM, OFM, OBLR, and Navel Orangeworm (https://www.semios.com/solutions/insect-pest-management/).	Semios internal technicians verify counts before publishing daily reports to the grower dashboard.	Bundled per-acre SaaS lease (includes frost, soil moisture, variable-rate mating disruption, and traps).
FarmSense FlightSensor (FarmSense, USA)	Continuous real-time (24/7 event-driven, hourly summaries). No camera—uses an optical-acoustic "light curtain" tunnel sensor (https://farmsense.io/about-us).	Infrared optical emitter and receiver array creating a light curtain across an attractant tunnel.	Tiny internal battery + solar panel; 4 to 5 years continuous field life without maintenance (https://www.postharvest.com/podcast/leslie-hickle-farmsense-ep-36).	Direct wireless / cellular telemetry to cloud; sends lightweight event/classification payloads rather than images.	Edge signal processing + Cloud ML. Measures wingbeat frequency, harmonics, and body shadow obstruction as insect flies through tunnel.	Validated with USDA/university entomologists; academic literature notes pass-through sensors risk counting the same uncaptured individual multiple times (https://www.researchgate.net/publication/355318381_A_cheap_electronic_sensor_automated_trap_for_monitoring_the_flight_activity_period_of_moths).	No photo to review. Grower relies entirely on algorithmic wingbeat classification (no sticky cards used).	Subscription lease: approx. \$300/\text{season} per sensor (https://greyb.com/blog/detecting-pests-using-ai/).
DTN / Spensa Z-Trap (Spensa Tech / DTN, USA)	Continuous real-time event counting. No camera—uses a proprietary bio-impedance electrified rod sensor (https://www.globalagtechinitiative.com/in-field-technologies/connectivity/technology-takes-field-scouting-to-the-next-level/).	No lighting required; pheromone lure draws target moths into contact with vertical metal rods surrounding the lure.	Rechargeable LiFePO4 / Li-ion battery operating for up to 6 months per charge; optional solar panel (https://www.mdpi.com/2077-0472/12/10/1721).	Cellular or local wireless relay to DTN cloud platform.	Edge bio-impedance detection. Electrified rods stun/kill the insect upon contact and measure electrical impedance signature (size/capacitance).	Evaluated in US row and orchard crops; prone to false positives when non-target insects of similar body mass contact the rods.	No visual image review. Counts are logged numerically into the MyDTN / Spensa portal; manual check requires emptying the collection bucket.	Annual hardware + DTN agronomic subscription fee.
CropVue Automated Delta Trap (CropVue Tech, Canada)	Daily image capture. High-resolution RGB camera with integrated lighting (https://biologicalag.com.au/products/cropvue-automated-delta-traps).	Integrated LED lighting inside a ruggedized Delta trap body.	Integrated solar panel on trap roof + internal rechargeable battery.	Direct local cellular connectivity + onboard GPS for auto-location.	Cloud inference (CropVue Cloud). Distinguishes target pests (CM, OFM) on sticky base from non-targets.	Validated in partnership with the Okanagan-Kootenay Sterile Insect Release (OKSIR) program in BC ($310k CAAIN project) (https://caain.ca/projects/orchard-pest-management/).	Web portal allows visual inspection of sticky card images and count verification.	Commercial dealer quote / seasonal service model.
xFarm Electronic Trap (xFarm Technologies, Italy/Switzerland)	1 photo/day (programmable intervals). 16 MP camera photographing a 20 \times 15\text{ cm} sticky sheet (https://www.researchgate.net/publication/388811374_New_tools_to_monitor_Scaphoideus_titanus_the_main_vector_of_phytoplasmas_associated_with_Flavescence_doree_in_vineyards).	Enclosed box trap (28 \times 20 \times 20\text{ cm}) with internal illumination.	3.7\text{ V}, 3500\text{ mAh} lithium battery + 1.5\text{ W} (11.2 \times 8.4\text{ cm}) solar panel.	Direct 4\text{G} cellular connectivity + GPS reception.	Cloud inference on xFarm platform; bounding-box detection and temporal tracking across daily captures.	Evaluated alongside Trapview in 2023 vineyard trials for Scaphoideus titanus.	Users inspect 16 MP images and bounding boxes in the xFarm app.	Annual SaaS + hardware purchase/lease.

Second-Order Architectural Trade-Offs in Commercial Systems

Measured Results: Empirical evaluations of commercial systems reveal a sharp divergence between laboratory marketing claims and field reality. While Trapview markets a database of over 30 million validated images across 60+ species (https://trapview.com/), an independent field study by Preti et al. (2021) testing commercial Trapview smart traps baited with a 5-component pheromone-kairomone lure for codling moth (Cydia pomonella) in Italian apple and pear orchards demonstrated that while total physical moth captures were statistically indistinguishable from standard orange delta traps ($10.7 \pm 1.7$ vs. $6.3 \pm 1.1$ adults/trap, $P = 0.903$), the correlation ($R^2$) between the automated algorithm counts and manual on-screen counts degraded severely whenever non-target insects were captured (https://www.researchgate.net/publication/351210617_Remote_monitorin[span_40](start_span)[span_40](end_span)g_of_Cydia_pomonella_adults_among_an_assemblage_of_nontargets_in_sex_pheromone-kairomone-baited_smart_traps). Specifically, the presence of look-alike tortricids (such as the carnation tortrix, $F = 91.18$), apple clearwing moths, shadow anomalies from the lure, aggregations of shed moth scales on the glue, and double-counting of single codling moths whose wings were expanded caused significant false positives (https://www.researchgate.net/publication/351210617_Remote_monitoring_of_Cydia_pomonella_adults_among_an_assemblage_of_nontargets_in_sex_pheromone-kairomone-baited_smart_traps). Conversely, a 2026 four-country study across Italy, France, Portugal, and Slovenia on pine processionary moth (Thaumetopoea pityocampa) found that automated camera traps detected first moth arrivals $5.2$ to $10.3\text{ days}$ earlier than conventional weekly manual traps in forest habitats ($p < 0.05$) and achieved a two-fold higher detection rate during the first four weeks of low-density flight (https://open-research-europe.ec.europa.eu/articles/6-421, https://ore.eu/ore/article/view/1616).

Engineering Synthesis (Opinion): Commercial vendors have learned that pure computer vision on sticky liners cannot be trusted blindly in commercial integrated pest management (IPM) without a human safety net. Consequently, both Trapview and Semios employ human-in-the-loop (HITL) verification, with Trapview guaranteeing human specialist verification within $\le 24\text{ hours}$ (https://trapview.com/, https://www.semios.com/solutions/insect-pest-management/). Non-imaging traps like FarmSense and Spensa Z-Trap eliminate sticky-card saturation and power-hungry image uploads, achieving 4–5 year battery lives (https://www.postharvest.com/podcast/leslie-hickle-farmsense-ep-36), but they sacrifice visual auditability: when an entomologist or grower sees an unexpected spike at 3:00 AM, there is no photograph to verify whether the trigger was a target codling moth, a non-target leafroller, or an insect repeatedly flying in and out of the optical tunnel (https://www.researchgate.net/publication/35531838[span_87](start_span)[span_87](end_span)1_A_cheap_electronic_sensor_automated_trap_for_monitoring_the_flight_activity_period_of_moths). For Orchard Sentinel, retaining high-resolution sticky-card photography with an explicit human review queue (review_queue in server/sentinel_server/) is architecturally superior to non-imaging sensors because getting the sustained-catch biofix right to within a day requires visual confirmation of the first $2\text{--}5$ moths (uploaded:00_ARGON_BRIEF.md).

2. Academic Literature on Automated Tortricid & Sticky-Trap Counting (2018–2026)

Academic research on automated monitoring of codling moth (Cydia pomonella), oriental fruit moth (Grapholita molesta), and related tortricid pests has progressed from early Raspberry Pi and Movidius/OpenCV blob detectors (2019–2021) to ultra-low-power RISC-V/ARM microcontroller edge inference and specialized YOLO architectures (2022–2026) (https://www.mdpi.com/2077-0472/12/10/1721, https://arxiv.org/html/2408.15911v2).

Summary of Key Academic Studies (2018–2026)

Study & Year	Target Pest(s)	Hardware & Imaging Setup	CV / ML Method	Dataset Size	Reported Accuracy	Documented Failures & Limitations
Brunelli et al. (2019) & Segalla et al. (2020) (https://www.mdpi.com/2077-0472/12/10/1721)	Codling moth (Cydia pomonella)	Raspberry Pi + Pi Camera + Intel Movidius NCS; LoRa modem; 9\text{ Ah} battery (2019). Greyscale 244 \times 324\text{ px} camera + LoRa (2020).	Grayscale smoothing, edge extraction, OpenCV blob detector \rightarrow VGG16 or LeNet classifier.	Field sticky trap patches	94.38% precision, 92.6% recall (Brunelli VGG16); LeNet outperformed VGG16 in Segalla.	Active execution took >50\text{--}62\text{ s} drawing >400\text{ mA} (10.73\text{ mA}/cycle avg), limiting a 1820\text{ mAh} LiPo to 169 cycles; 244 \times 324 grayscale lacked fine wing detail.
Preti et al. (2021a & 2021b) (https://pdfs.semanticscholar.org/4e81/397aa7cd033c5fba2d29aba9e2d3617a8f68.pdf, https://www.researchgate.net/publication/351210617_Remote_monitoring_of_Cydia_pomonella_adults_among_an_assemblage_of_nontargets_in_sex_pheromone-kairomone-baited_smart_traps)	Codling moth (C. pomonella) among non-targets	Custom ESP32 + 5 MP OV5648 (2592 \times 1944), SIM800 GSM, 2 \times graphene batteries (7.2\text{ V}, 3500\text{ mA}) + 2 \times 2\text{ W} solar (€375 BOM); also evaluated Trapview.	Java server pipeline using ImageJ1, MorphoLibJ, and DeepLearning4J; plus Trapview cloud CNN.	4 field experiments, subsets of 50+ multi-species liners.	High detection in clean traps, but low R^2 correlation in multi-species kairomone traps.	Custom Java algorithm overestimated real captures by 1.5x to 3x. False positives driven by carnation tortrix, moth wing scales on glue, lure shadows, and double-counting moths with open wings.
Sütő (2021 & 2022) (https://www.mdpi.com/2077-0472/12/10/1721, https://arxiv.org/html/2408.15911v2)	Codling moth (C. pomonella)	Embedded sticky paper trap; evaluated Raspberry Pi 3B, Nvidia Jetson TX2, and STM32H7 (480\[span_135](start_span)[span_135](end_span)[span_139](start_span)[span_139](end_span)text{ MHz}).	Selective Search (SS) region proposal kernel + MobileNetV2 / 3.2M-param DNN; also tested RetinaNet.	40+ test trap images (640 \times 480) + DIRT/Leeds negative datasets.	93.1% AP on 640 \times 480 trap images; 82% accuracy when quantized onto STM32H7 MCU.	Lightweight RetinaNet failed to run on Raspberry Pi 3B due to memory/compute limits; accuracy dropped from >93\% to 82\% when constrained to MCU memory.
Pérez-Aparicio et al. (2021) (https://www.researchgate.net/publication/355318381_A_cheap_electronic_sensor_automate[span_46](start_span)[span_46](end_span)d_trap_for_monitoring_the_flight_activity_period_of_moths)	Oriental fruit moth (Grapholita molesta)	Raspberry Pi Zero W + 8 MP Pi Camera NoIR v2.1 + IR LED; 12\text{ V}, 7\text{ Ah} lead-acid battery + 20\text{ W} solar (€150 BOM).	High-temporal-resolution image capture stored to microSD for diel flight periodicity analysis.	Continuous diurnal/nocturnal field series of G. molesta.	Successfully resolved short dusk/night diel sexual activity windows of OFM.	Power supply + frame weighed 7.47\text{ kg} (3.47\text{ kg} frame + 4\text{ kg} battery/solar), requiring a galvanized steel bar driven into the ground; no wireless upload.
Schrader et al. (2022) (https://www.mdpi.com/2075-1702/10/1/52)	Codling moth (C. pomonella)	Arducam IoTai ESP32-CAM + 2 MP OV2640 + 180^\circ fisheye clip-on lens; 350\text{ mAh} LiPo; microSD storage (\$32.67 BOM).	Daily wake at 10:00 AM (15\text{ s} active time), sleep mode; manual/offline evaluation of capture dates.	20 traps deployed over 10–14 days in commercial Fuji/Granny Smith orchards.	Sufficient to determine individual moth capture dates at 0.1\text{ cm/pixel}.	Stored images at 320 \times 240\text{ px} (1\text{ mm/px})—far too coarse for CM vs. OFM species ID; no wireless transmission; internal ESP32 RTC lost time on every power reset.
Čirjak et al. (2023) (https://www.mdpi.com/2077-0472/13/5/961)	Codling moth (C. pomonella), other insects, debris	Smart trap with on-site edge processing; transmits only detection results to server.	Deep Neural Network (DNN) multi-class object detector evaluated via confusion matrix.	430 sticky pad photos from 3 apple orchards: 8,142 CM, 5,458 other insects, 8,177 debris (21,777 total labels).	99.3% accuracy in detecting codling moth on test split.	High power draw during once-daily active inference (up to 5\text{ W} peak on embedded processor) (https://arxiv.org/html/2408.15911v2); dataset not publicly shared.
Flórián et al. (2023) (https://pmc.ncbi.nlm.nih.gov/articles/PMC10145081/)	Lepidoptera / orchard and forest moths	ZooLog VARL funnel trap prototype with optical/camera probe; daily cellular upload.	Artificial Neural Network (ANN) real-time catch detection compared against daily manual checks.	Multi-species field season catches.	84% to 92% average detection accuracy (90% for larger moths, >60\% for small species).	Accuracy degraded significantly on smaller-bodied moth species (~60\%), requiring further catching-efficiency calibration.
Rusci et al. / GreenWaves GAP9 Study (2024) (https://arxiv.org/html/2408.15911v2)	Codling moth (C. pomonella)	GreenWaves GAP9 RISC-V SoC (1+9 cores, NE16 CNN accelerator, 1.5\text{ MB} L2 RAM at 0.65\text{ V}) + LoRa + 1000\text{ mAh} battery.	Benchmarked Viola-Jones vs. GMM + MobileNetV2 / CNN on near-dataset and far-dataset.	Field sticky pad dataset (<1.6\% non-targets; 27 non-target objects total, only 3 in test split).	93% accuracy, +27\% higher than Viola-Jones on far-dataset; only 4.85\text{ mJ} per inference.	Dataset contained almost no look-alike non-target insects (<1.6\%), so model was trained exclusively as a single-class C. pomonella detector.
YOLOv9-TrapPest (2025) (https://www.frontiersin.org/journal[span_170](start_span)[span_170](end_span)s/plant-science/articles/10.3389/fpls.2025.1521594/full)	7 agricultural pheromone-trapped pests	Smart electro-killing pheromone trap with rotating bottom collection tray.	YOLOv9-TrapPest with AKConv backbone module + cascaded DBTNet-101 bilinear classifier.	Multi-species smart trap dataset	98.3% mAP50, 97.5% recall (outperformed YOLOv8m by +4.1\% and DETR by +4.5\%).	Electric shock module broke pest limbs and charred/fragmented bodies, causing standard YOLOv8/v9 models to fail until AKConv and DBTNet-101 were added.
YOLOv5–v12 Codling Moth Benchmark (2025/2026) (https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0346415, https://scifiniti.com/3104-4719/2/2025.0026)	Codling moth (C. pomonella)	IoT smart sticky trap pipeline	Benchmarked YOLOv5m through YOLOv12m; proposed Improved YOLOv10-m with C3 and ConvTranspose2d upsampling.	Standardized codling moth sticky trap test set.	Improved YOLOv10-m achieved 100% precision/recall (89\text{--}94\% confidence).	Baseline YOLOv6m, YOLOv8m, and YOLOv12m generated false positives (50\text{--}58\% confidence), while baseline YOLOv10m suffered false negatives (83\% recall) on small/intricate moth features before upsampling layers were added.

Synthesis of Academic Failures and Domain Lessons

Measured Results: Across the 2018–2026 literature, four recurring failure modes dominate field deployments. First, non-target tortricid confusion and severe over-counting occur whenever traps are deployed in biologically diverse orchards. Preti et al. (2021) demonstrated that when traps catch non-target tortricids alongside C. pomonella, classical blob-plus-classifier pipelines (MorphoLibJ, ImageJ1, and DeepLearning4J) overestimate true captures by $1.5\times$ to $3\times$, while commercial CNNs suffer steep drops in $R^2$ (https://www.mdpi.com/2077-0472/12/10/1721, https://www.researchgate.net/publication/351210617_Remote_monitoring_of_Cydia_pomonella_adults_among_an_assemblage_of_nontargets_in_sex_pheromone-kairomone-baited_smart_traps). Conversely, studies claiming $>93\text{--}99\%$ accuracy, such as Rusci et al. (2024), explicitly acknowledge that non-target objects represented $<1.6\%$ of their dataset, with only 3 non-target objects present in the entire test split (https://arxiv.org/html/2408.15911v2).

Second, optical geometry inside standard delta traps forces a harsh trade-off between field of view (FOV) and spatial resolution. Schrader et al. (2022) proved mathematically and empirically that fitting a camera inside the $110\text{ mm}$ apex of a standard delta trap to image a $17.8 \times 17.8\text{ cm}$ ($178\text{ mm}$) liner requires an optical FOV of approximately $97^\circ$ (https://www.researchgate.net/publication/357740818_An_[span_173](start_span)[span_173](end_span)Open-Source_Low-Cost_Imaging_System_Plug-In_for_Pheromone_Traps_Aiding_Remote_Insect_Pest_Population_Monitoring_in_Fruit_Crops). Their $180^\circ$ clip-on fisheye lens solved the geometry problem without cutting the trap roof, but storing $320 \times 240$ images yielded $1\text{ mm/pixel}$ ($0.1\text{ cm/pixel}$), which is roughly $15\times$ coarser than the $\sim 15\text{ px/mm}$ needed to distinguish C. pomonella (wingspan $15\text{--}20\text{ mm}$, coppery apical spot) from G. molesta (wingspan $11\text{--}14\text{ mm}$, mottled gray-brown lacking the bronzed patch) (uploaded:00_ARGON_BRIEF.md, https://www.mdpi.com/2075-1702/10/1/52). Earlier foundational work by Guarnieri et al. established that $>2\text{ MP}$ ($3\text{ MP}$ across the full liner, or $\sim 10\text{--}12\text{ px/mm}$) is the minimum resolution threshold to resolve codling moth morphological traits (https://www.mdpi.com/2077-0472/12/10/1721).

Third, biological predation, decay, and insect movement on sticky liners violate static background assumptions. The 2026 Open Research Europe multi-country study documented that predators (such as birds, wasps, ants, and spiders) actively feed on or remove trapped moths from sticky liners, leaving behind detached wings or antennae that confuse object detectors, while high catch density reduces exposed glue and increases the movement rate (%) of newly arriving moths across sequential frames (https://open-research-europe.ec.europa.eu/articles/6-421). Finally, standard YOLO downsampling layers lose small insect features unless modified. The 2026 PLOS ONE benchmark demonstrated that out-of-the-box YOLOv10-m misses $17\%$ of codling moths ($83\%$ recall) and YOLOv6-m, YOLOv8-m, and YOLOv12-m produce low-confidence false positives ($50\text{--}58\%$) unless high-resolution feature upsampling (ConvTranspose2d + C3) or tiling is incorporated (https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0346415).

3. ESP32-Camera Field Deployments: Hardware, Optics, RF, and Firmware

Deploying the Freenove ESP32-S3-WROOM CAM (N8R8: 8 MB Flash, 8 MB OPI PSRAM) inside an Alpha Scents delta trap introduces specific electrical, optical, radio-frequency, and firmware constraints (uploaded:00_ARGON_BRIEF.md, https://www.mdpi.com/1999-4893/17/11/476, https://robotforge.org/articles/lesson-1-meet-the-esp32).

3.1 Real Deep-Sleep Current and Battery Budget on the Freenove ESP32-S3 CAM

Measured Results: While the bare ESP32-S3-WROOM-1 module datasheet specifies a deep-sleep current of $\sim 14\ \mu\text{A}$ (and $\sim 2\text{ mA}$ in light sleep) (https://forum.dronebotworkshop.com/esp32-esp8266/power-consumption-esp32/), real-world bench measurements of the Freenove ESP32-S3-WROOM CAM development board reveal an actual deep-sleep current of $17.5\text{ mA}$ to $22\text{ mA}$ ($17.5\text{ mA}$ mean measured by McDaid 2024; $18\text{ mA}$ at $5\text{ V}$ and $22\text{ mA}$ at $3.8\text{ V}$ battery input measured on ESP32-S3 CAM dev boards) (https://davidmcdaid.wordpress.com/2024/01/22/iot-squirrel-house/, https://forum.dronebotworkshop.com/esp32-esp8266/power-consumption-esp32/). This $1,250\times$ penalty over the bare module is caused by four parasitic hardware draws on the Freenove board. Even when the ESP32-S3 is in esp_deep_sleep_start(), the 24-pin DVP camera module remains powered on the $3.3\text{ V}$ rail and draws $\sim 2\text{ mA}$ continuously (https://forum.dronebotworkshop.com/esp32-esp8266/power-consumption-esp32/). Simultaneously, the hardwired onboard power indicator LED consumes $\sim 1.66\text{ mA}$ (https://forum.dronebotworkshop.com/esp32-esp8266/power-consumption-esp32/), while the onboard AMS1117-style LDO voltage regulator and the always-powered CH343 USB-to-serial chip consume $10\text{--}14\text{ mA}$ of quiescent current (https://forum.dronebotworkshop.com/esp32-esp8266/power-consumption-esp32/, https://www.reddit.com/r/esp32/comments/16strnx/trying_to_design_a_solar_batterypowered_esp32/, https://robotforge.org/articles/lesson-1-meet-the-esp32). Furthermore, preserving GPIO states during deep sleep on Espressif chips adds $\ge 250\ \mu\text{A}$ of leakage if strapping or pull-up pins are held active (https://docs.circuitpython.org/en/stable/shared-bindings/alarm/).

During active capture and Wi-Fi transmission, the Freenove ESP32-S3-WROOM CAM draws an average of $160\text{--}300\text{ mA}$ ($205\text{ mA}$ average measured over an 8-hour continuous Wi-Fi capture test), with instantaneous current peaks of $\sim 340\text{ mA}$ when Wi-Fi initializes and transmits (https://www.mdpi.com/1999-4893/17/11/476, https://www.reddit.com/r/esp32/comments/16strnx/trying_to_design_a_solar_batterypowered_esp32/, https://www.skillsdirectory.com/skills/alexex1993-esp32s3-cam-40pin).

Engineering Synthesis & Battery Calculation (Answering Open Question #6):
To evaluate how long a trap node can run on a 1S2P $18650$ lithium-ion pack with $5,000\text{ mAh}$ usable capacity ($6,000\text{ mAh}$ nominal derated to $83\%$ for temperature and cutoff voltage) taking $6$ photos per day, consider a $15\text{-second}$ wake duration per photo (https://www.mdpi.com/2075-1702/10/1/52) at $250\text{ mA}$ average active current (including LED flash):


$$\text{Active Charge per Day} = 6 \times \left(\frac{15\text{ s}}{3600\text{ s/h}}\right) \times 250\text{ mA} = 6.25\text{ mAh/day}$$

| Power Configuration Scenario | Sleep Current ($I_{\text{sleep}}$) | Sleep Charge / Day ($23.975\text{ h}$) | Active Charge / Day ($6 \times 15\text{ s}$) | Total Daily Charge | Estimated Battery Life ($5,000\text{ mAh}$ Usable) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Scenario A: Unmodified Freenove ESP32-S3 CAM Board | $18.0\text{ mA}$ | $431.55\text{ mAh}$ | $6.25[span_242](start_span)[span_242](end_span)[span_247](start_span)[span_247](end_span)\text{ mAh}$ | $437.80\text{ mAh/day}$ | $11.4\text{ days}$ |
| Scenario B: Desoldered Power LED + Camera PWDN Sleep + Low-$I_q$ 3.3V Buck-Boost | $0.50\text{ mA}$ | $11.99\text{ mAh}$ | $6.25\text{ mAh}$ | $18.24\text{ mAh/day}$ | $274.1\text{ days}$ (Full Season) |
| Scenario C: External High-Side P-MOSFET / TPL5110 Timer Cutting Board Power | $0.05\text{ mA}$ | $1.20\text{ mAh}$ | $6.25\text{ mAh}$ | $7.45\text{ mAh/day}$ | $671.1\text{ days}$ |

Without power-gating the Freenove board or bypassing its LDO and USB bridge, a $2 \times 18650$ battery pack will deplete in under two weeks (https://davidmcdaid.wordpress.com/2024/01/22/iot-squirrel-house/, https://forum.dronebotworkshop.com/esp32-esp8266/power-consumption-esp32/). Adding a high-side MOSFET switch triggered by an external RTC/timer chip eliminates the $431.55\text{ mAh/day}$ parasitic sleep loss and allows a single $2 \times 18650$ pack to power the trap for an entire 6-month growing season without requiring solar panels (https://robotforge.org/articles/lesson-1-meet-the-esp32).

3.2 Camera Sensor Comparison: OV3660 vs. OV5640

Both the OV3660 ($3\text{ MP}$) and OV5640 ($5\text{ MP}$) use the standard 24-pin DVP ribbon connector and are drop-in hardware compatible with the Freenove ESP32-S3-WROOM CAM (https://www.espboards.dev/blog/esp32-camera-modules-compared/, https://www.waveshare.com/esp32-s3-cam-ov5640.htm).

Specification	OmniVision OV3660 (Current Node)	OmniVision OV5640 (Planned Upgrade)	Impact on Orchard Sentinel Sticky-Card Imaging
Max Resolution	2048 \times 1536 (3.15\text{ MP}) (https://www.sincerefirst.com/product/ov3660-cmos-sensor-3mp-hd-image-dvp-camera-module-for-general-esp32-embedded-imaging)	2592 \times 1944 (5.04\text{ MP}) (https://electropeak.com/esp32-cam-plus-development-board-with-ov5640-camera)	At a 198 \times 174\text{ mm} full-card view, OV3660 yields \sim 8.8\text{--}10.3\text{ px/mm}; OV5640 yields \sim 11.2\text{--}13.1\text{ px/mm}.
Standard & Wide Lens FOV Options	Standard 66^\circ\text{--}70.8^\circ diagonal (f = 2.38\text{ mm}); also manufactured in 160^\circ wide-angle (https://www.sincerefirst.com/product/ov3660-cmos-sensor-3mp-hd-image-dvp-camera-module-for-general-esp32-embedded-imaging, https://store.roboticsbd.com/colorgesturecamera/3929-ov3660-3mp-camera-module-24pin-160-wide-angle-for-esp32-cam-robotics-bangladesh.html).	Standard 66^\circ\text{--}76.6^\circ; widely available in 120^\circ wide and 150^\circ diagonal (130^\circ\text{ H} \times 106^\circ\text{ V}) fixed-focus (https://www.sincerefirst.com/product/hd-image-esp32-camera-module-series-for-embedded-vision-devices, https://www.accio.com/plp/esp32-cam-module-image).	A 120^\circ\text{--}130^\circ FOV lens is required to see the full 174 \times 198\text{ mm} card from the 110\text{ mm} delta trap roof peak without protruding above the roof (https://www.mdpi.com/2075-1702/10/1/52).
Focus Mechanism	Fixed-Focus (manual thread adjustment if unglued).	Available in both Fixed-Focus (10\text{ cm to }\infty) and VCM Autofocus (AF) (https://www.sincerefirst.com/product/hd-image-esp32-camera-module-series-for-embedded-vision-devices, https://www.espboards.dev/blog/esp32-camera-modules-compared/).	At a fixed 110\text{--}140\text{ mm} working distance, Fixed-Focus calibrated to 10\text{--}15\text{ cm} (or VCM AF locked once) gives sharp macro detail (https://www.espboards.dev/blog/esp32-camera-modules-compared/).
Low-Light & Dynamic Range	Superior low-light sensitivity and cleaner contrast in dim scenes (https://www.espboards.dev/blog/esp32-camera-modules-compared/).	Poorer low-light performance; noisier in shadows and weaker contrast handling in backlit scenes (https://www.espboards.dev/blog/esp32-camera-modules-compared/, https://github.com/RomanLut/hx-esp32-cam-fpv).	Inside a dark red delta trap lit by an LED or shaded canopy light, OV3660 produces less chroma noise per pixel than OV5640.
Thermal & Voltage Behavior	Runs warm if left streaming, cool in single-shot mode (https://www.reddit.com/r/esp32/comments/1ou74mm/on_the_overheating_issues_of_the_ov3660_and/).	Prone to severe overheating on ESP32-CAM-style boards because boards supply 3.3\text{ V} to the 2.8\text{ V max} digital rail and 1.2\text{ V} to the 1.5\text{ V} core (https://www.reddit.com/r/esp32/comments/1ou74mm/on_the_overheating_issues_of_the_ov3660_and/).	For single-shot duty cycling (<15\text{ s} awake), overheating is avoided, but during continuous setup preview (setup_preview), an OV5640 will rapidly overheat to >70^\circ\text{C}.

Engineering Synthesis (Answering Open Question #2):
Morphologically, distinguishing C. pomonella ($15\text{--}20\text{ mm}$ wingspan, $\sim 8\text{--}10\text{ mm}$ body length resting) from G. molesta ($11\text{--}14\text{ mm}$ wingspan, $\sim 5\text{--}7\text{ mm}$ resting) requires resolving the coppery-bronze apical patch on the forewing tip of CM versus the uniform salt-and-pepper gray of OFM (uploaded:00_ARGON_BRIEF.md). At the OV3660's current narrow $66^\circ$ view ($115 \times 85\text{ mm}$ coverage, $\sim 18\text{ px/mm}$), an OFM moth spans $\sim 110 \times 70\text{ pixels}$—more than enough for BioCLIP or a CNN, but it misses $56\%$ of the sticky card's area ($9,775\text{ mm}^2$ vs. $34,452\text{ mm}^2$ total card area) (uploaded:00_ARGON_BRIEF.md). Missing more than half the liner risks delaying the sustained-catch biofix whenever the first moths land near the card perimeter. Switching to a $120^\circ$ Fixed-Focus OV5640 ($2592 \times 1944$) mounted at the $110\text{ mm}$ roof peak captures $100\%$ of the $174 \times 198\text{ mm}$ card at $\sim 11.5\text{--}12.5\text{ px/mm}$ (producing $75 \times 50\text{ px}$ crops for OFM and $115 \times 75\text{ px}$ crops for CM), which satisfies both the full-card biofix requirement and the $>2\text{ MP}$ morphological threshold established by Guarnieri et al. (https://www.mdpi.com/2077-0472/12/10/1721, https://www.accio.com/plp/esp32-cam-module-image).

3.3 Wi-Fi Range Through Orchard Foliage vs. ESP-NOW and LoRa

Measured Results: Radio propagation at $2.4\text{ GHz}$ inside a leafed-out apple orchard suffers severe attenuation because water inside leaves absorbs $2.4\text{ GHz}$ microwave energy while branches and trunks cause scattering and multipath fading (https://www.preprints.org/manuscript/202602.0666). Empirical orchard channel modeling establishes a path loss exponent of $n \approx 3.0$ in dense orchards and a linear vegetation attenuation slope of $0.45\text{ dB/m}$ at $2.4\text{ GHz}$ (https://www.preprints.org/manuscript/202602.0666). Using Weissberger's modified exponential decay model, $L_W\text{ (dB)} = 1.33 f^{0.284} d_f^{0.588}$ (where $f$ is frequency in GHz and $d_f$ is foliage depth in meters for $14\text{ m} < d_f \le 400\text{ m}$), $100\text{ m}$ of orchard foliage introduces $25.73\text{ dB}$ of excess foliage loss at $2.45\text{ GHz}$, compared to $19.16\text{ dB}$ at $868\text{ MHz}$—a $6.57\text{ dB}$ penalty against $2.4\text{ GHz}$ (https://llufb.llu.lv/conference/AICT/2012/ELSTS_AICT2012.pdf, https://www.scribd.com/document/176853773/Investigations-of-Foliage-Effect-on-Modern-Wireless-Communication-Systems). Furthermore, the UHF/microwave in-leaf versus out-of-leaf model demonstrates a $7.0\text{ dB}$ increase in baseline attenuation ($26.2\text{ dB}$ in-leaf vs. $19.2\text{ dB}$ out-of-leaf) once spring foliage emerges, while wind velocities as low as $15\text{ km/h}$ through four rows of trees cause dynamic multipath fades of $15\text{ dB}$ at rates up to $50\text{ dB/s}$ every $0.5\text{ seconds}$ (https://www.scribd.com/document/176853773/Investigations-of-Foliage-Effect-on-Modern-Wireless-Communication-Systems). Consequently, while unobstructed outdoor $2.4\text{ GHz}$ Wi-Fi can reach $150\text{ m}$, mid-canopy orchard deployments with PCB antennas reliably span only $20\text{ to }100\text{ m}$ unless the hub antenna is elevated just above the canopy ($2.5\text{--}3.0\text{ m}$) so signals diffract over the tree rows (https://www.preprints.org/manuscript/202602.0666, https://pmc.ncbi.nlm.nih.gov/articles/PMC11053448/).

Wireless Protocol	Operating Band & Data Rate	Orchard Range (Mid-Canopy)	Transport & Reassembly Complexity for 250\text{ KB} JPEG	Energy / Airtime Cost per Photo
Standard Wi-Fi (802.11b/g/n)	2.4\text{ GHz}; 11\text{--}150\text{ Mbps}	20\text{--}100\text{ m} (150\text{ m} with elevated AP)	Low: Native TCP/HTTP POST directly to Raspberry Pi hostapd AP.	Low (\sim 0.5\text{ s} transfer time; \sim 3.5\text{ s} total wake with association).
ESP-NOW (esp_now / LR Mode)	2.4\text{ GHz}; 250\text{ kbps}\text{--}1\text{ Mbps}	80\text{--}180\text{ m}	High: Requires custom C++ fragmentation into 250\text{--}1400\text{ B} packets, std::map mutex reassembly, and an extra ESP32 receiver wired to the Hub Pi.	Lowest (eliminates Wi-Fi association/DHCP overhead).
LoRa (Sub-GHz)	868\text{ / }915\text{ MHz}; 0.3\text{--}27\text{ kbps}	500\text{--}2,000+\text{ m}	Prohibitive for raw JPEGs: Suitable only for byte-sized pest count payloads after on-node edge inference.	Very High for images: Measured at 1\text{ mJ/byte} (12.7\text{ J} for 12.7\text{ KB}; \sim 250\text{ J} for 250\text{ KB}).

Engineering Synthesis (Answering Open Question #7):
Keeping HTTP over $2.4\text{ GHz}$ Wi-Fi (802.11b/g/n) is the optimal architecture for a single-season student team because the Raspberry Pi hub natively supports an access point (hostapd), TCP handles packet retransmission automatically during $15\text{ dB}$ wind fades, and a $200\text{--}300\text{ KB}$ JPEG uploads in under half a second (uploaded:00_ARGON_BRIEF.md). Switching to ESP-NOW would require writing and debugging custom C++ packet fragmentation, sequence numbering, mutex-protected std::map reassembly, and custom ACK/retry logic across $\sim 200\text{--}1,200$ fragments per image, plus adding a dedicated ESP32 receiver dongle onto the Raspberry Pi Hub (https://github.com/Boyyt357/ESP32-CAM-ESPNOW-V2-ESP32CAM-to-ESP32-VIDEO-TX-AND-RX). Similarly, LoRa is viable only if deep learning inference runs inside the trap so that only byte-sized counts are transmitted (https://arxiv.org/html/2408.15911v2, https://www.mdpi.com/2077-0472/12/10/1721). Instead of changing protocols, the team should attach an external IPEX/U.FL dipole antenna to the Freenove board and elevate the Hub's Wi-Fi AP antenna to $2.5\text{--}3.0\text{ m}$ height above the tree canopy (https://www.preprints.org/manuscript/202602.0666).

3.4 OTA Firmware Updates with Rollback, Offline Timekeeping, and PSRAM/JPEG Settings

In ESP-IDF and Arduino-ESP32 deployments, over-the-air (OTA) firmware updates must be protected against field bricking by configuring the $8\text{ MB}$ N8R8 flash partition table with two OTA application slots (ota_0 and ota_1, e.g., $3\text{ MB}$ each) alongside an otadata partition (https://documentation.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/ota.html?, https://robotforge.org/articles/lesson-1-meet-the-esp32). Enabling CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE causes the bootloader to boot a newly downloaded firmware image in the ESP_OTA_IMG_PENDING_VERIFY state (https://documentation.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/ota.html?). On the first wake after an OTA update, the firmware must initialize the camera, connect to the hub Wi-Fi, and receive a valid 200 OK check-in before calling esp_ota_mark_app_valid_cancel_rollback() (https://documentation.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/ota.html?). If a flawed firmware build panics, brown-outs, or fails to connect to Wi-Fi, the watchdog resets the chip and the bootloader automatically rolls back to the previous working slot.

For offline timekeeping, Schrader et al. (2022) documented that the ESP32's internal RTC resets to epoch $0$ whenever battery power is interrupted, and its internal $150\text{ kHz}$ RC oscillator drifts across orchard diurnal temperature swings (https://www.researchgate.net/publication/357740818_An_Open-Source_Low-Cost_Imaging_System_Plug-In_for_Pheromone_Traps_Aiding_Remote_Insect_Pest_Population_Monitoring_in_Fruit_Crops). Because the Orchard Sentinel node syncs its clock from the Hub Raspberry Pi (gateway.py) on every HTTP check-in (uploaded:00_ARGON_BRIEF.md), two failure modes must be guarded: if the Hub Pi reboots without cellular connectivity and lacks a hardware battery-backed RTC (such as a DS3231 on the Hub), the Hub itself will serve stale fake-hwclock time to all nodes; and when a node cannot reach the Hub over Wi-Fi, it should compute sleep duration from its monotonic sleep schedule and store boot_count plus relative elapsed seconds in RTC slow memory (RTC_DATA_ATTR) so the Hub can reconstruct true capture timestamps upon reconnection.

For PSRAM and camera initialization, the Freenove N8R8 board uses Octal SPI (OPI) PSRAM ($8\text{ MB}$) (https://robotforge.org/articles/lesson-1-meet-the-esp32). In PlatformIO or Arduino, BOARD_HAS_PSRAM and qio_opi memory mode must be enabled so camera_config_t can allocate frame buffers in external PSRAM (.fb_location = CAMERA_FB_IN_PSRAM[span_201](start_span)[span_201](end_span), .pixel_format = PIXFORMAT_JPEG, .frame_size = FRAMESIZE_QSXGA [$2592 \times 1944$] for OV5640 or FRAMESIZE_QXGA [$2048 \times 1536$] for OV3660, .jpeg_quality = 10, .fb_count = 2, and .grab_mode = CAMERA_GRAB_LATEST) (https://www.accio.com/plp/esp32-cam-module-image, https://robotforge.org/articles/less[span_263](start_span)[span_263](end_span)on-1-meet-the-esp32). Crucially, on the 40-pin Freenove ESP32-S3-WROOM CAM, calling Wire.begin() or SPI.begin() with default arguments clobbers the camera data lines because the S3 Arduino variant defaults to SDA=8, SCL=9 and MOSI=11, MISO=13, SCK=12, SS=10, which are wired directly to camera pins D2, D1, D0, PCLK, D4, D3 (https://www.skillsdirectory.com/skills/alexex1993-esp32s3-cam-40pin). Furthermore, because the CMOS sensor's Auto-Exposure (AEC) and Auto-White-Balance (AWB) require $3\text{--}5$ frames to stabilize after turning on the LED flash—especially inside a bright red delta trap that skews red-channel gain—firmware must turn on the LED, wait $300\text{ ms}$, dummy-read and discard $3$ frame buffers (esp_camera_fb_get() / esp_camera_fb_return()), and only transmit the 4th buffer (uploaded:00_ARGON_BRIEF.md).

4. Hub and Server IoT Architecture Patterns



4.1 Store-and-Forward, Idempotent Uploads, and MQTT vs. HTTP for Photos

In hobbyist ESP32-CAM tutorials, images are frequently Base64-encoded and published over MQTT (https://www.reddit.com/r/esp32/comments/16strnx/trying_to_design_a_solar_batterypowered_esp32/). In professional IoT camera engineering, Base64-over-MQTT is an anti-pattern: Base64 inflates payload size by $33\%$, requires allocating a second contiguous buffer in PSRAM, and forces the MQTT broker to buffer multi-hundred-kilobyte messages in memory. Orchard Sentinel's current choice of raw HTTP POST (JPEG binary + JSON metadata header) from the ESP32-S3 to gateway.py and from uploader.py to FastAPI aligns with industry best practice (uploaded:00_ARGON_BRIEF.md). HTTP supports chunked streaming directly from the camera frame buffer (esp_camera_fb_get()->buf), native TLS/HTTPS, and clear status codes (200 OK, 201 Created, idempotent 200 OK on duplicate capture_uid, 429 Too Many Requests, and 503 Service Unavailable).

To prevent file corruption on the Fieldhouse Hub (gateway.py), incoming uploads should never be streamed directly into the active queue/ directory where uploader.py might read a half-written JPEG or where a power drop could leave a truncated file. Instead, gateway.py should write incoming bytes to a temporary staging file (queue/.tmp_<capture_uid>.jpg), flush the file descriptor to disk via os.fsync(), and execute an atomic POSIX rename (os.replace()) into queue/<capture_uid>.jpg (uploaded:00_ARGON_BRIEF.md). Once uploader.py receives a 200 OK from the server and moves the file to sent/, a ring-buffer cleanup routine should prune the oldest acknowledged files whenever disk utilization exceeds $80\%$. On the server side, enforcing a UNIQUE constraint on the deterministic capture_uid guarantees idempotency so that cellular retries never trigger duplicate background worker jobs or double-count insects (uploaded:00_ARGON_BRIEF.md).

4.2 Device Provisioning, Per-Device Keys, and Fleet Health Monitoring

Orchard Sentinel already authenticates trap uploads using per-trap API keys (uploaded:00_ARGON_BRIEF.md). On the ESP32-S3, the device's unique API key, device_id, and Wi-Fi credentials should be flashed once into the dedicated NVS (Non-Volatile Storage) partition rather than hardcoded in main.cpp, allowing identical firmware binaries to be deployed across all traps via OTA. Additionally, the open web server used during setup_preview on the ESP32 must enforce a strict auto-shutdown timeout (e.g., $5\text{ minutes}$ after a physical button boot) so that it cannot remain open indefinitely in the orchard draining the battery or exposing an unauthenticated camera stream (uploaded:00_ARGON_BRIEF.md).

In agricultural field deployments, silent hardware failures—such as a depleted battery, a clogged solar panel, or an unplugged fieldhouse hub—are frequent (https://pmc.ncbi.nlm.nih.gov/articles/PMC7506980/). The FastAPI server should run a scheduled background check every $30\text{ minutes}$ that dispatches an automated email, SMS, or push notification whenever a Hub fails to send a heartbeat for $>2\text{ hours}$, whenever an individual trap node misses $\ge 2$ consecutive scheduled wake windows, or whenever telemetry reports a battery voltage below $3.45\text{ V}$ (for Li-ion) or $3.15\text{ V}$ (for LiFePO4) (uploaded:00_ARGON_BRIEF.md, https://pmc.ncbi.nlm.nih.gov/articles/PMC7506980/).

4.3 SQLite in Production (WAL + Litestream) vs. When to Move to Postgres

Measured Results: Modern single-server production architectures (including Rails 8 Solid Queue and production FastAPI applications) have demonstrated that SQLite in Write-Ahead Logging (WAL) mode handles thousands of sequential writes per second and sub-40ms reads on local solid-state storage ($15\text{--}40\text{ ms}$ page renders on local SQLite versus $30\text{--}80\text{ ms}$ on remote PostgreSQL) by eliminating network round-trips (https://justinmckelvey.com/blog/sqlite-in-production-ready-for-your-startup). For Orchard Sentinel—even at $200\text{ traps}$ taking $6\text{ photos/day}$ ($1,200\text{ writes/day}$, or $<0.02\text{ writes/second}$)—SQLite's single-writer concurrency model is nowhere near saturation (https://justinmckelvey.com/blog/sqlite-in-production-ready-for-your-startup).

However, running SQLite in production with a FastAPI web process and a background CV worker thread (worker.py) requires disciplined transaction boundaries and continuous off-site replication. To prevent SQLITE_BUSY ("database is locked") errors, every database connection must execute PRAGMA journal_mode=WAL;, PRAGMA synchronous=NORMAL;, and PRAGMA busy_timeout=5000;, and the background CV worker must never hold an open write transaction while executing multi-second OpenCV or BioCLIP inference (uploaded:00_ARGON_BRIEF.md, https://litestream.io/guides/wal-truncate-threshold/). To eliminate single-file data loss risk—since Orchard Sentinel currently has no backups (uploaded:00_ARGON_BRIEF.md)—the server should run Litestream (v0.5+) as a background sidecar process (https://litestream.io/how-it-works/, https://zircote.com/field-notes/sqlite-wal-s3-replication/). Litestream hooks into the SQLite -wal file and streams committed WAL pages packaged as TXID-indexed LTX files every $1\text{ second}$ to S3-compatible object storage such as Cloudflare R2, which costs $\$0.015/\text{GB/month}$ with zero egress fees (https://litestream.io/how-it-works/, https://justinmckelvey.com/blog/sqlite-in-production-ready-for-your-startup, https://zircote.com/field-notes/sqlite-wal-s3-replication/). Litestream's three-tier checkpoint strategy (MinCheckpointPageN, CheckpointInterval, and emergency brake TruncatePageN: 121359 [$\sim 500\text{ MB}$]) executes non-blocking PASSIVE checkpoints (sqlite3_wal_checkpoint_v2()) that keep the WAL file around $\sim 4\text{ MB}$ without blocking application writes (https://litestream.io/guides/wal-truncate-threshold/). Migrating to PostgreSQL is unnecessary for this season and is only warranted when scaling to multiple horizontally distributed application servers writing concurrently or when multi-tenant enterprise features are required (https://justinmckelvey.com/blog/sqlite-in-production-ready-for-your-startup, https://zircote.com/field-notes/sqlite-wal-s3-replication/).

4.4 Cheap Cloud Hosting with HTTPS for a Student Project

To expose the Orchard Sentinel dashboard and upload API on the public internet with valid HTTPS and a custom domain (uploaded:00_ARGON_BRIEF.md), two low-cost options stand out. If the team keeps the Raspberry Pi 5 as the server (ideally booting from an NVMe SSD rather than an SD card), installing Cloudflare Tunnel (cloudflared) as a systemd service creates an outbound-only encrypted tunnel to Cloudflare's edge network (https://shattered.io/cloudflare-tunnel-setup-guide-2026/, https://clawtank.dev/blog/openclaw-raspberry-pi-setup). This requires zero open router ports, bypasses campus or residential NAT/CGNAT, and provides automatic public HTTPS on a $\$10/\text{year}$ domain at zero monthly hosting cost (https://programmingpercy.tech/blog/free-secure-self-hosting-using-cloudflare-tunnels/, https://dev.to/arisdolanan/home-labs-2-setup-raspberry-pi-with-cloudflare-zero-trust-managed-tunnel-k7). Alternatively, if the team moves off the Pi 5 to a cloud virtual private server (VPS) such as a Hetzner Cloud ARM64/x86 instance ($\sim\$4.50/\text{month}$) or a DigitalOcean/AWS Lightsail node covered by GitHub Student Developer Pack credits, placing Caddy in front of FastAPI provides automatic Let's Encrypt HTTPS provisioning and renewal while Litestream replicates SQLite to Cloudflare R2 (https://github.com/kzahel/yepanywhere/blob/main/docs/project/remote-access.md, https://justinmckelvey.com/blog/sqlite-in-production-ready-for-your-startup).

5. Cellular Data Budgets and Bandwidth Optimization Strategies

5.1 Monthly Cellular Data Math for Orchard Sentinel

Measured Pricing: Commercial IoT cellular providers operate on two primary pricing structures: 1NCE offers a Lifetime Flat IoT SIM plan providing $500\text{ MB}$ over 10 years for a one-time payment of $\$14$ with no monthly fees (https://trafalgarwireless.com/blog/wi-fi-vs-cellular-iot-connectivity/), whereas Hologram charges $\$1.00/\text{month}$ per SIM plus $\$0.03/\text{MB}$ ($\$30/\text{GB}$) (https://www.kajeet.com/en/blog/best-iot-sim-cards-us-provider-comparison, https://onomondo.com/blog/top-7-iot-connectivity-providers-for-large-fleets/). For higher-bandwidth hubs, standard prepaid MVNO LTE data plans (such as US Mobile or Tello) provide $1\text{--}5\text{ GB/month}$ for $\$5\text{--}\$15/\text{month}$.

Assuming a baseline schedule of $6\text{ photos/day}$ ($180\text{ photos/month}$, or $1,080\text{ photos}$ over a 6-month May–October season) plus $15\%$ HTTP/TLS/Tailscale VPN protocol and heartbeat overhead, the monthly cellular data budget scales across five pipeline strategies as follows (uploaded:00_ARGON_BRIEF.md):

Compression / Pipeline Strategy	Payload Size per Capture	Data per Trap per Month (180 captures + 15% overhead)	10-Trap Orchard Monthly Data	Monthly Cost on Hologram (\$0.03/\text{MB})	Fits 1NCE \$14 (500\text{ MB}) SIM for 6-Month Season?
1. Raw Full-Frame 5 MP JPEG (Quality 8, Uncompressed)	600\text{ KB}	124.2\text{ MB/mo}	1,242\text{ MB/mo}	\$3.73/\text{trap} (\$38.26 for 10 traps)	No (745\text{ MB/season} per trap)
2. Tuned 3–5 MP JPEG (Quality 12, Cropped to Liner)	220\text{ KB}	45.5\text{ MB/mo}	455\text{ MB/mo}	\$1.37/\text{trap} (\$14.65 for 10 traps)	Yes, for 1 trap (273\text{ MB/season}), No for a multi-trap Hub
3. Pessl iSCOUT / Trapview Schedule (1–2 photos/day, Quality 12)	220\text{ KB}	7.6\text{--}15.2\text{ MB/mo}	76\text{--}152\text{ MB/mo}	\$0.23\text{--}\$0.46/\text{trap}	Yes (45\text{--}91\text{ MB/season} per trap)
4. Hub Change Detection (1 Daily Full Reference + 50\text{ KB} ROI Crops on New Arrivals)	220\text{ KB} (1\times) + 15\text{ KB} avg (5\times)	19.2\text{ MB/mo}	192\text{ MB/mo}	\$0.58/\text{trap}	Yes (115\text{ MB/season} per trap)
5. Full Hub/Edge Inference (Send JSON Counts + Uncertain Crops Only)	2\text{ KB} JSON + occasional 25\text{ KB} crop	1.8\text{ MB/mo}	18\text{ MB/mo}	\$0.05/\text{trap}	Yes, easily (10.8\text{ MB/season} per trap; 10 traps = 108\text{ MB})

5.2 Proven Techniques Commercial Products Use to Shrink Data Budgets

Commercial and academic systems compress cellular bandwidth through four complementary mechanisms. First, commercial systems align capture frequency with insect flight biology: both Pessl iSCOUT (1 photo/day on GPRS, 1–3 photos/day on LTE) and Trapview (1 photo/day at midday) recognize that codling moths fly primarily at dusk ($20:00\text{ to }00:00$) and secondarily at dawn (https://metos.global/en/iscout/, https://www.researchgate.net/publication/351210617_Remote_monitoring_of_Cydia_pomonella_adults_among_an_assemblage_of_nontargets_in_sex_pheromone-kairomone-baited_smart_traps, https://www.researchgate.net/publication/357740818_An_Open-Source_Low-Cost_Imaging_System_Plug-In_for_Pheromone_Traps_Aiding_Remote_Insect_Pest_Population_Monitoring_in_Fruit_Crops). Reducing Orchard Sentinel's capture frequency from 6 photos/day to 2 photos/day (e.g., 07:00 AM after the night flight and 16:00 PM as a backup) cuts both cellular data and active ESP32 battery consumption by $66\%$ with zero loss in daily biofix resolution.

Second, because a wide-angle lens captures surrounding trap walls and tray margins alongside the sticky liner (https://www.researchgate.net/figure/Trap-box-and-diagrams-of-power-supply-The-trap-box-A-consists-of-an-outer-plastic-box_fig1_355318381), the mains-powered Fieldhouse Hub (gateway.py) can use the 4 ArUco corner markers to homography-crop the image strictly to the $174 \times 198\text{ mm}$ card and re-encode it into WebP (quality=80), shrinking payload size by $\sim 2.5\times$ before cellular upload. Third, because zero new moths arrive on most intermediate daytime wakes, the Hub can perform frame differencing between consecutive ArUco-aligned images, uploading one full-card reference image per day and transmitting only small $256 \times 256\text{ px}$ high-resolution crops ($\sim 15\text{--}25\text{ KB}$) around newly appeared blobs on intermediate wakes. Fourth, academic systems by Čirjak et al. (2023) and Rusci et al. (2024) run object detection on the edge and transmit only count metadata or cropped detections, which Rusci et al. demonstrated reduces transmission energy and bandwidth by $6.5\times$ (https://arxiv.org/html/2408.15911v2, https://www.mdpi.com/2077-0472/13/5/961).

6. Orchard Sentinel Pipeline vs. Industry Best Practice: Gap Analysis

6.1 Architectural Gap Table

Comparing the current Orchard Sentinel pipeline described in Sections 2 and 3 of 00_ARGON_BRIEF.md against commercial and academic best practices highlights eight primary operational gaps (uploaded:00_ARGON_BRIEF.md):

Subsystem	Orchard Sentinel Current State (00_ARGON_BRIEF.md)	Commercial / Academic Best Practice	Operational Gap & Field Risk
1. Node Deep-Sleep Power Architecture	Freenove ESP32-S3-WROOM CAM powered directly on 1S lithium pack (docs/wiring.md).	Power-gated sensor/MCU rails drawing <50\text{--}250\ \mu\text{A} in sleep (https://arxiv.org/html/2408.15911v2, https://pmc.ncbi.nlm.nih.gov/articles/PMC7506980/).	Critical: Unmodified Freenove S3 CAM boards draw 17.5\text{--}22\text{ mA} in deep sleep due to the LDO, CH343 USB chip, power LED, and 2\text{ mA} camera leak, draining a 2 \times 18650 pack in \sim 11\text{ days} (https://davidmcdaid.wordpress.com/2024/01/22/iot-squirrel-house/, https://forum.dronebotworkshop.com/esp32-esp8266/power-consumption-esp32/).
2. Camera Optics & Trap Geometry	OV3660 (3\text{ MP}, 66^\circ FOV) at 110\text{ mm} sees only 115 \times 85\text{ mm} (44\% of the 174 \times 198\text{ mm} card).	Full-liner coverage via \ge 97^\circ\text{--}120^\circ wide-angle lens or raised camera turret (https://www.mdpi.com/2075-1702/10/1/52, https://www.accio.com/plp/esp32-cam-module-image).	Critical: Missing 56\% of the sticky liner will miss early-season moths landing near the card perimeter, delaying biofix detection by days.
3. Scale Reference & Alignment	OpenCV grid finder measures the printed 25\text{ mm} grid; misreads 5 of 10 insect-occupied photos (32\text{--}63\text{ px/mm} instead of 15.3) and locks in first photo's scale.	Fixed rigid geometry + 4 corner fiducial markers (ArUco/AprilTag) for homography warp and deterministic px/mm scale.	Critical: Moths landing on grid intersections break Hough/line-spacing detection, corrupting crop scaling and track matching across photos.
4. Lighting & Glare Control	Single bare white LED; 10\text{--}13\% of the glossy sticky card is blown out by specular glare.	Diffused, off-axis or ring illumination (or ambient translucent roof diffusion like iSCOUT) (https://metos.global/en/iscout/, https://davidmcdaid.wordpress.com/2024/01/22/iot-squirrel-house/).	High: Specular glare hides moths in the center of the card and creates bright blob edges that trigger false-positive detections.
5. Counting New Arrivals & Unannounced Liner Swaps	Tracks each insect across all of a liner's photos; liner swap requires a manual button press.	Homography-aligned sequential change detection + automatic "card emptied" detection when >70\% of prior tracks vanish.	High: If a scout swaps a sticky liner without pressing the button, or if a bird/wasp removes a moth (https://open-research-europe.ec.europa.eu/articles/6-421), track state and liner_age become corrupted.
6. Database Backups & Concurrency	Single SQLite file in WAL mode on Pi 5 with zero backups; API and worker threads share the DB.	SQLite WAL + busy_timeout + short write transactions + Litestream continuous LTX replication to S3/R2 (https://litestream.io/how-it-works/).	High: SD card corruption or accidental deletion on the Pi 5 loses the entire season's field data and entomologist labels.
7. Time Sync Without Internet	Node takes time from Hub (gateway.py); firmware drift-rate correction rarely runs.	Hardware battery-backed RTC (DS3231) on the Hub Pi + monotonic boot_count/sequence tags on the ESP32 (https://www.mdpi.com/2075-1702/10/1/52).	Medium: If the fieldhouse loses mains power while cellular is down, the Hub Pi boots with stale time and poisons the timestamps of all ESP32 nodes.
8. Fleet Health & Dead-Man Alerts	Status logged to status.jsonl, but no automated alerts when a hub or trap goes offline.	Automated SMS/email/webhook alerts on missed check-ins, low battery voltage (<3.45\text{ V}), or disk saturation (https://pmc.ncbi.nl[span_235](start_span)[span_235](end_span)m.nih.gov/articles/PMC7506980/).	Medium: A trap with a dead battery or detached solar wire can go unnoticed for a week during the critical CM biofix window.

6.2 Direct Synthesis on Open Architectural & Hardware Questions (Questions 3, 4, 6, 7, 12)

Regarding scale calibration (Question 3), relying on the printed $25\text{ mm}$ grid is provably fragile once insects, shed wing scales, or specular glare occlude the grid intersections, as evidenced by the $50\%$ failure rate ($5\text{ of }10$ insect-occupied photos reading $32\text{--}63\text{ px/mm}$ instead of $15.3\text{ px/mm}$) already documented in the project README (uploaded:00_ARGON_BRIEF.md, https://www.researchgate.net/publication/351210617_Remote_monitoring_of_Cydia_pomonella_adults_among_an_assemblage_of_nontargets_in_sex_pheromone-kairomone-baited_smart_traps). Because the 3D-printed camera mount and liner tray establish a fixed physical distance between the lens and the card, the pipeline should use 4 ArUco fiducial markers on the tray corners for homography alignment and scale, backed by a hardcoded physical scale constant ($15.3\text{ px/mm}$ for OV3660, $\s[span_190](start_span)[span_190](end_span)[span_195](start_span)[span_195](end_span)im 12.0\text{ px/mm}$ for wide OV5640) clamped to a strict $\pm 10\%$ sanity window (uploaded:00_ARGON_BRIEF.md).

For counting new arrivals and handling unannounced liner swaps (Question 4), combining homography-aligned pairwise change detection between photo $t$ and photo $t-1$ with multi-frame track persistence is much more resilient than spatial tracking alone, particularly when predators partially remove moths or when high catch densities cause insects to shift (uploaded:00_ARGON_BRIEF.md, https://open-research-europe.ec.europa.eu/articles/6-421). To detect a sticky liner that was replaced without pressing the reset button, the worker should check whether photo $t$ has normal illumination and valid corner alignment while $\ge 70\%$ of confirmed insect tracks from photo $t-1$ (when $N_{t-1} \ge 3$) have vanished at their registered coordinates; when that condition holds, the pipeline should automatically close the old liner session, initialize a fresh liner record (liner_age = 0), and log a review notice (uploaded:00_ARGON_BRIEF.md).

On the hardware side, the most likely failure in the first week of field deployment (Question 12) is twofold: first, rapid battery depletion and brownout resets (ESP_RST_BROWNOUT) within $10\text{--}12\text{ days}$ caused by the unmodified Freenove ESP32-S3 CAM board's $17.5\text{--}22\text{ mA}$ deep-sleep draw and $340\text{ mA}$ Wi-Fi + LED current spikes (Question 6) (https://davidmcdaid.wordpress.com/2024/01/22/iot-squirrel-house/, https://forum.dronebotworkshop.com/esp32-esp8266/power-consumption-esp32/, https://www.skillsdirectory.com/skills/alexex1993-esp32s3-cam-40pin); and second, immediate scale and tracking corruption when the first captured moths land on the $25\text{ mm}$ grid lines (uploaded:00_ARGON_BRIEF.md). Meanwhile, once orchard foliage emerges, $2.4\text{ GHz}$ Wi-Fi attenuation ($0.45\text{ dB/m}$, or $25.73\text{ dB}$ over $100\text{ m}$) and $15\text{ dB}$ wind fades will drop packets from mid-canopy PCB antennas unless an external dipole antenna is used on the trap and the Hub AP antenna is elevated to $2.5\text{--}3.0\text{ m}$ above the canopy (Question 7) (https://www.preprints.org/manuscript/202602.0666, https://llufb.llu.lv/conference/AICT/2012/ELSTS_AICT2012.pdf, https://www.scribd.com/document/176853773/Investigations-of-Foliage-Effect-on-Modern-Wireless-Communication-Systems).

7. Prioritized Recommendations for the Student Team (Ranked by Value per Effort)

The following table summarizes the highest-leverage engineering interventions for a student team with a single field season, ranked by value per effort (S = under 1 day, M = 2–5 days, L = over 1 week) in accordance with Section 4 of 00_ARGON_BRIEF.md (uploaded:00_ARGON_BRIEF.md).

Rank & ID	Recommendation Title	Severity	Confidence	Effort	Target Subsystem (Where)
1. CV-01	Clamp Grid Scale Finder to Physical Bounds and Add ArUco Homography Fallback	Critical	Sure	S	server/sentinel_server/pipeline/detect.py
2. HW-01	Eliminate Freenove ESP32-S3 Deep-Sleep Parasitic Drain (18\text{--}22\text{ mA} to <0.1\text{ mA})	Critical	Sure	S	device/esp32-node/src/main.cpp & docs/wiring.md
3. HW-02	Swap Narrow 66^\circ OV3660 for a 120^\circ Wide-Angle OV5640 and Add an LED Diffuser	Critical	Sure	S	hardware/scad/camera_mount.scad & main.cpp
4. OPS-01	Deploy Litestream Continuous WAL Backup to Cloudflare R2 and Cloudflare Tunnel HTTPS	High	Sure	S	server/sentinel_server/ on Raspberry Pi 5
5. SRV-01	Add Automatic Unannounced Liner-Swap Detection and Fleet Dead-Man Alerts	High	Sure	M	worker.py, track.py, & gateway.py
6. DEV-01	Harden Hub Store-and-Forward Queue and Add a Hardware RTC to the Fieldhouse Pi	Medium	Sure	S	device/sentinel_device/gateway.py & uploader.py

CV-01 · Clamp Grid Scale Finder to Physical Bounds and Add ArUco Homography Fallback

Severity: critical | Confidence: Sure | Effort: S | Where: server/sentinel_server/pipeline/detect.py (grid scale estimation and liner scale locking). Based on the documented evidence that "the grid finder misreads photos with insects on them (5 of 10 read 32–63 px[span_334](start_span)[span_334](end_span)/mm instead of 15.3); the scale check trusts a liner's first photos" (uploaded:00_ARGON_BRIEF.md), a moth, leaf, or glare spot occluding the $25\text{ mm}$ printed grid lines on the first photo of a liner causes the grid-spacing estimator to lock in a harmonic multiple ($32\text{--}63\text{ px/mm}$ instead of $15.3\text{ px/mm}$). This resizes all downstream insect crops by $2\times\text{--}4\times$, breaking both spatial tracking distance thresholds and BioCLIP classification (uploaded:00_ARGON_BRIEF.md). Fix: Because the camera mount sits at a fixed physical distance from the liner floor ($110\text{--}140\text{ mm}$), the true optical scale cannot physically vary by more than $\pm 10\%$. Immediately clamp any measured grid scale outside $[13.8, 16.8]\text{ px/mm}$ (for OV3660) or $[10.5, 13.5]\text{ px/mm}$ (for wide OV5640) back to the nominal calibrated constant (DEFAULT_PX_PER_MM = 15.3), compute a rolling median across the first 3 photos rather than locking photo 1, and use cv2.aruco.ArucoDetector on the 4 tray corner markers as the primary homography and scale source (uploaded:00_ARGON_BRIEF.md).

HW-01 · Eliminate Freenove ESP32-S3 Deep-Sleep Parasitic Drain (18–22 mA to <0.1 mA)

Severity: critical | Confidence: Sure | Effort: S | Where: device/esp32-node/src/main.cpp and node power wiring (docs/wiring.md). The project brief notes that the trap uses a "Freenove ESP32-S3-WROOM CAM (N8R8: 8 MB flash, 8 MB PSRAM)... Power (docs/wiring.md): 1S lithium pack (18650s or LiFePO4)" (uploaded:00_ARGON_BRIEF.md), and empirical bench measurements show that unmodified Freenove S3 CAM boards draw $17.5\text{--}22\text{ mA}$ in deep sleep (https://davidmcdaid.wordpress.com/2024/01/22/iot-squirrel-house/, https://forum.dronebotworkshop.com/esp32-esp8266/power-consumption-esp32/). What goes wrong is that the onboard LDO, CH343 USB bridge, power LED ($1.66\text{ mA}$), and unswitched camera rail ($2\text{ mA}$) drain $431.5\text{ mAh/day}$ during esp_deep_sleep_start(), exhausting a $2 \times 18650$ pack in $\sim 11.4\text{ days}$ and triggering brownout resets (ESP_RST_BROWNOUT) when Wi-Fi and the LED flash fire simultaneously (https://forum.dronebotworkshop.com/esp32-esp8266/power-consumption-esp32/, https://www.skillsdirectory.com/skills/alexex1993-esp32s3-cam-40pin). Fix: Place a nano-power timer/RTC switch (such as an Adafruit TPL5110 breakout or a PCF8563 RTC alarm driving a high-side P-channel MOSFET) between the battery regulator and the Freenove 3V3 pin so the entire board is unpowered ($<0.05\text{ mA}$) between wakes (https://robotforge.org/articles/lesson-1-meet-the-esp32), add a $470\text{--}1000\ \mu\text{F}$ low-ESR capacitor across 3V3 and GND to buffer the $340\text{ mA}$ Wi-Fi TX peak, and reduce capture frequency from 6 photos/day to 2–3 photos/day as validated by Pessl iSCOUT (https://metos.global/en/iscout/).

HW-02 · Swap Narrow 66° OV3660 for a 120° Wide-Angle OV5640 and Add an LED Diffuser

Severity: critical | Confidence: Sure | Effort: S | Where: Trap camera hardware (hardware/sca[span_245](start_span)[span_245](end_span)[span_250](start_span)[span_250](end_span)d/camera_mount.scad) and device/esp32-node/src/main.cpp. The brief states that "Its OV3660 (3 MP) lens is narrow (~66°): from 110 mm it sees only ~115 × 85 mm of the card... 10–13 % of the card is blown out by glare, and there's no diffuser yet" (uploaded:00_ARGON_BRIEF.md). Consequently, $56\%$ of the sticky liner is outside the camera's field of view, risking missed biofix catches near the card perimeter, while direct specular reflection from the bare LED blinds $10\text{--}13\%$ of the card's center (uploaded:00_ARGON_BRIEF.md). Fix: Install a $120^\circ$ Fixed-Focus ($10\text{ cm}$ focus distance) 5 MP OV5640 24-pin DVP camera module ($\sim\$6\text{--}\$10$) (https://www.espboards.dev/blog/esp32-camera-modules-compared[span_264](start_span)[span_264](end_span)/, https://www.accio.com/plp/esp32-cam-module-image), which captures $100\%$ of the $174 \times 198\text{ mm}$ liner from the $110\text{ mm}$ roof apex without requiring a housing that protrudes above the roof (https://www.mdpi.com/2075-1702/10/1/52). Pair this with a $1.5\text{ mm}$ matte white polycarbonate/PTFE diffuser plate in front of the LED angled $30^\circ$ off-axis, and discard 3 warmup frames in main.cpp after turning on the LED so auto-exposure and white balance stabilize before capturing the transmitted JPEG (uploaded:00_ARGON_BRIEF.md).

OPS-01 · Deploy Litestream Continuous WAL Backup to Cloudflare R2 and Cloudflare Tunnel HTTPS

Severity: high | Confidence: Sure | Effort: S | Where: server/sentinel_server/ deployment environment on the Raspberry Pi 5. The brief notes "Server: FastAPI + SQLite on a Raspberry Pi 5... backups (none exist today)... Not built yet: a cloud server with HTTPS and a domain" (uploaded:00_ARGON_BRIEF.md). Without off-site replication, an SD card failure or accidental deletion on the Pi 5 destroys the entire season's database (https://justinmckelvey.com/blog/sqlite-in-production-ready-for-your-startup), and unencrypted HTTP exposes API keys and login credentials in plaintext. Fix: Run litestream replicate as a systemd service streaming the SQLite WAL (truncate-page-n: 121359, 1s sync) to a free Cloudflare R2 bucket alongside a nightly rclone sync job for data/photos/ (https://litestream.io/guides/wal-truncate-threshold/, https://justinmckelvey.com/blog/sqlite-in-production-ready-for-your-startup). Simultaneously, install cloudflared as a systemd service to expose FastAPI over automatic Cloudflare HTTPS with zero open router ports (https://shattered.io/cloudflare-tunnel-setup-guide-2026/), and set PRAGMA busy_timeout = 5000; on all SQLite connections while keeping CV inference strictly outside database write transactions (https://litestream.io/guides/wal-truncate-threshold/).

SRV-01 · Add Automatic Unannounced Liner-Swap Detection and Fleet Dead-Man Alerts

Severity: high | Confidence: Sure | Effort: M | Where: server/sentinel_server/pipeline/worker.py, track.py, and device/sentinel_device/gateway.py. As documented in the brief ("Already built: tracking across photos... Not built yet: alerts (including 'hub[span_59](start_span)[span_59](end_span) offline')... Consider: a liner replaced without the button press") (uploaded:00_ARGON_BRIEF.md), if a grower or scout replaces a sticky card without pressing the physical button on the trap node, the tracker attempts to match new captures against vanished tracks, corrupting liner_age and cumulative counts; meanwhile, a silent hub or node failure goes unnoticed. Fix: In worker.py and track.py, check whether photo $t$ has normal mean intensity and valid corner alignment while $\ge 70\%$ of confirmed insect tracks from photo $t-1$ (when $N_{t-1} \ge 3$) no longer contain foreground blobs; when triggered, automatically close the prior liner session, initialize a new liner record (liner_age = 0), and flag the transition in the review queue (uploaded:00_ARGON_BRIEF.md). Add a 30-minute background monitor that dispatches an email/SMS alert whenever a Hub heartbeat is $>2\text{ hours}$ old, a trap misses $2$ consecutive scheduled check-ins, or battery voltage falls below $3.45\text{ V}$ (https://pmc.ncbi.nlm.nih.gov/articles/PMC7506980/).

DEV-01 · Harden Hub Store-and-Forward Queue and Add a Hardware RTC to the Fieldhouse Pi

Severity: medium | Confidence: Sure | Effort: S | Where: device/sentinel_device/gateway.py and uploader.py. The brief states that the "Hub Raspberry Pi (no camera, mains power, always on) device/sentinel_device/gateway.py stores photos to disk (queue/ -> sent/), serves each node its wake schedule and the time" (uploaded:00_ARGON_BRIEF.md). If the fieldhouse loses mains power while cellular internet is unreachable, the Raspberry Pi Hub reboots without NTP synchronization and serves a stale clock (fake-hwclo[span_335](start_span)[span_335](end_span)ck) to every ESP32 node on check-in (https://www.mdpi.com/2075-1702/10/1/52); additionally, an unpruned sent/ folder can exhaust disk space over a season or uploader.py can read a partially written JPEG from queue/. Fix: Attach a $\$5$ DS3231 battery-backed I2C RTC module onto the Fieldhouse Hub Pi's GPIO header so the Hub maintains accurate UTC time across power outages even offline (https://www.mdpi.com/2075-1702/10/1/52). In gateway.py, write incoming ESP32 uploads to queue/.tmp_<capture_uid>.jpg, call os.fsync(), and atomically rename (os.replace()) to queue/<capture_uid>.jpg, and add a pruning step in uploader.py that deletes the oldest acknowledged files in sent/ whenever free disk space falls below $2\text{ GB}$ (uploaded:00_ARGON_BRIEF.md).




Sources used in the report
  An Open-Source Low-Cost Imaging System Plug-In for Pheromone

  An Open-Source Low-Cost Imaging System Plug-In for Pheromone

  Accelerating Image-based Pest Detection on a Heterogeneous Multi

  Codling Moth Monitoring with Camera-Equipped Automated Traps

  Automatic Pest Monitoring Systems in Apple Production under

  TECHNICAL BROCHURE - COLEAD

  Large testing of AI-based camera traps on a forest defoliating pest in

  iMETOS iSCOUT® TRAPS - Smart Protect

  iSCOUT – METOS by Pessl Instruments

  Pessl Instruments corporate presentation 2023/2024

  Trapview: Real-Time Smart Pest Monitoring And Forecasting

  (PDF) New tools to monitor Scaphoideus titanus, the main vector of

  Large testing of AI-based camera traps on... | Open Research Europe

  Codling Moth Monitoring with Camera-Equipped Automated Traps

  BOOK OF ABSTRACTS OF ALL THE POSTERS - ECPA 2025

  State-of-the-Art Internet of Things in Protected Agriculture

  State-of-the-Art Internet of Things in Protected Agriculture - PMC

  A cheap electronic sensor automated trap for monitoring the flight

  CropVue Automated Delta Traps - Biological Ag

  Future semiochemical control of codling moth, Cydia pomonella

  Startups to showcase irrigation, robotics, pest-detection tech June 26

  AI-Enabled Smart Trap System to Enhance Orchard Pest Management

  About FarmSense | Real-Time Insect Monitoring Experts

  Leslie Hickle - FarmSense - Ep 36 - PostHarvest Technologies

  Stuck in the Past | Why Farmers Are Replacing Sticky Traps with

  AI Object Detection in Agriculture: Precision Pest Management

  FarmSense Revolutionizes Pest Control With Next-Generation

  How AI is used to Detect Pests and Save Crops in Agriculture - GreyB

  Spensa Technologies - Grokipedia

  Technology Takes Field Scouting To The Next Level

  An IoT Smart Rodent Bait Station System Utilizing Computer Vision

  Agri Articles (E-Magazine) 05(05) 2025

  DJ-075X Series Animal Behavior Infrared Camera Trap

  A technical survey on practical applications and guidelines for IoT

  Unraveling the periodicity of secondary growth in the Congo Basin

  (PDF) Remote monitoring of Cydia pomonella adults among an

  Research on a machine vision-based electro-killing pheromone

  Insect Pest Management Solutions - Semios

  Automatic Detection of Moths (Lepidoptera) with a Funnel Trap

  IOT Squirrel House - David McDaid Electronics

  Alarms and sleep — Adafruit CircuitPython documentation

  A Review on Resource-Constrained Embedded Vision Systems

  Trying to design a solar battery-powered ESP32 that operates 24/7

  Power consumption esp32 - DroneBot Workshop Forums

  Esp32s3 Cam 40pin (Grade A) - Claude Skill | Skills Directory

  On the overheating issues of the OV3660 and OV5640 camera

  OV3660 CMOS Sensor 3MP HD Image DVP Camera Module for

  ESP32 Cam Module Image: Best Options 2026

  ESP32 Camera Modules Compared: OV2640, OV5640, OV3660

  HD Image ESP32 Camera Module Series for Embedded Vision

  OV3660 3MP Camera Module 24Pin 160° Wide-angle for ESP32-CAM

  ESP32-CAM Plus Development Board With OV5640 Camera

  ESP32-S3 AIoT Camera Development Board, Integrated Audio Input

  GitHub - RomanLut/hx-esp32-cam-fpv

  Over The Air Updates (OTA) - Espressif Documentation

  WAL Truncate Threshold Configuration - Litestream

  How it works - Litestream

  SQLite in Production: Why It's Ready for Your Startup in 2026

  Can Replicated SQLite Carry Multi-Region, Per-Customer Apps?

  Wi-Fi vs Cellular IoT Connectivity: Which Is Better for Smart Devices?

  Best IoT SIM Cards: US Provider Comparison 2026-2027 - Kajeet

  Top 7 IoT connectivity providers for large fleets in 2026 - Onomondo

  Large testing of AI-based camera traps on a forest defoliating pest in

  iTRAKER PRO Non-invasive insect detection device

  Smartforests Canada: A Network of Monitoring Plots for Forest

  Harnessing the Internet of Things (IoT) for a Hyper-Connected Smart

  Cutting-Edge Sensing Allocations and Enhanced Wireless

  LATVIA UNIVERSITY OF AGRICULTURE

  Smart Sensors and Smart Data for Precision Agriculture: A Review

  Development of the Internet of smart orchard Things based on multi

  EfficientDet-4 Deep Neural Network-Based Remote Monitoring of

  Enhancing Pest Management in Precision Agriculture: Integration of

  Real-time codling moth monitoring using improved YOLOv10 and

  GitHub - Boyyt357/ESP32-CAM-ESPNOW-V2-ESP32CAM-to

  Cloudflare Tunnel Setup: 12 Steps, 45 Min [2026] - shattered.io

  Free Secure Self-Hosting Using Cloudflare Tunnels

  yepanywhere/docs/project/remote-access.md at main - GitHub

  Running OpenClaw on Raspberry Pi: The Complete Hardware and

  Setup Raspberry Pi with Cloudflare Zero Trust (Managed Tunnel)

  Monitoring System for Leucoptera malifoliella (O. Costa, 1836) and

  Fig. 1. Trap box and diagrams of power supply. The trap-box (A)

  Lesson 1: Meet the ESP32-S3 - RobotForge

  Foliage Impact on Wireless Systems | PDF | Microwave - Scribd




Sources read but not used
  Intelligent Battery-Designed System for Edge-Computing-Based

  Carrot Fact Sheet | SmartProtect H2020

  METOS by Pessl - RDO Equipment

  Product Portfolio - METOS Weather Stations

  Green Technology Book 2022. Solutions for climate change ... - WIPO

  SMART agriculture for innovative vegetable crop PROTECTion

  Artificial Intelligence and IoT-Based Technologies for Sustainable

  Smart Sensors and Smart Data for Precision Agriculture: A Review

  Web‐based automatic traps for early detection of alien wood‐boring

  Internet-of-Things (IoT)-Based Smart Agriculture - IEEE Xplore

  Evaluation of Machine Learning Approaches for Precision Farming

  on the biology and neuroethology of two tortricid moths

  California - Heyzine

  Faculty of Agriculture Dana Čirjak - Agronomski fakultet

  Automatic Pest Monitoring Systems in Apple Production under

  2025 ePLUS Report - OSU South Centers - The Ohio State University

  Fields of Expectation | Rethinking Precision Agriculture - FarmSense

  Improving the Efficiency of Your Pesticides - FarmSense

  Pest Monitoring to Protect Your Apples From Codling ... - FarmSense

  國立臺灣大學生農學院生物機電工程學系 博士論文 羅傑瑞 指導教授

  Comprehensive Automation for Specialty Crops Portfolio November

  Ecomatik/DE-Manufacturers-Dianjiang Group Limited

  Chronica Horticulturae 62/3 - ISHS

  Animal Infrared Camera Trap - Dianjiang Group Limited

  Identifying hotspot areas for biodiversity and ecosystem services in

  I REUNIÓN TRINACIONAL DE ECOLOGÍA - Zenodo

  (PDF) Automatic Pest Monitoring Systems in Apple Production under

  Advances in insect pest and disease monitoring and forecasting in

  A novel dataset and deep learning object detection benchmark for

  A Smart, Low-Cost Monitoring System for Sustainable Apple Farming

  Schematic drawing of the electronic trap (measures are in mm).

  Future semiochemical control of codling moth, Cydia pomonella

  Diel Periodicity in Males of the Navel Orangeworm (Lepidoptera

  PCB for an ESP32-C3 and ASRPRO Offline Voice-Controlled Car

  User manual - SolarOS

  (PDF) A Review on Resource-Constrained Embedded Vision

  ESP32 Camera: Best Modules & Uses in 2025 - Accio Work

  Buy Camera / Imaging Sensor and Modules Online in India at

  SQLite in Production: Modern Applications Guide 2026 | Pavan

  SQLite Litestream Replication in Production Guide - Matthews Wong

  sqlite-js-stream: Litestream Rewritten for Node.js | daily.dev

  Going Production-Ready with SQLite: How Litestream Makes It

  Getting Started - Litestream

  Streaming S3 replication for SQLite : r/golang - Reddit

  10 Best IoT SIM Providers in 2026: Features & Pricing - Pelion

  A technical survey on practical applications and guidelines for IoT

  All abstracts for ICOS Science Conference 2026

  Radio Characterization for ISM 2.4 GHz Wireless Sensor Networks

  Environment-Conditioned Diffusion Meta-Learning for Data-Efficient

  Using Data Augmentation to Improve the Generalization Capability

  A novel dataset and deep learning object detection benchmark for

  A Motor-Driven and Computer Vision-Based Intelligent E-Trap for

  IoT-Based Pest Detection in Agriculture Using Raspberry Pi and

  [PDF] A Novel Plug-in Board for Remote Insect Monitoring

  Smart Home Automation & Monitoring Hub - Circuit Digest

  GhostESP Changelog - Release Notes & Updates

  (PDF) Autonomous Navigation of Cloud-Controlled Quadcopters in

  ESPHome 2025.9.0: MIPI RGB displays and a camera JPEG encoder

  Autonomous Navigation of Cloud-Controlled Quadcopters in ... - arXiv

  audiocore – Support for audio samples - CircuitPython

  ESP-FAQ Handbook - Technical Documents

  How I Run My Entire Digital Life on a Raspberry Pi - Medium

  Catalogue of Products | PDF | Arduino | Microcontroller - Scribd

  Making a smart enclosure for the Original Prusa MK4 - Rudd-O.com

  ESP32S3 models for 3D printer - Printables.com

  Build · SporePrint

  Illuminating New Frontiers In Communication and Sensing with

  A Simplified Analytical Model to Predict the Specific Attenuation of a

  (PDF) Vegetation Effects on LoRa-Based Wireless Sensor

  Intelligent Circuits and Systems - OAPEN Library




Thoughts
