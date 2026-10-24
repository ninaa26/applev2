Grower and IPM Scout Requirements for Automated Lepidopteran Pest Monitoring Dashboards (Part D4)

1. Northeast US Phenology Models, Biofix Rules, and Spray Decision Logic

In the Northeastern United States, commercial tree-fruit management for the internal worm and leafroller complex—specifically codling moth (CM, Cydia pomonella), oriental fruit moth (OFM, Grapholita molesta), and obliquebanded leafroller (OBLR, Choristoneura rosaceana)—operates on a two-stage biological clock (uploaded:00_ARGON_BRIEF.md, https://newa.cornell.edu/crop-and-pest-management, https://nyshs.org/wp-content/uploads/2016/10/Obliquebanded-Leafroller-Management-for-Apple-Production-Investigating-Strategies-for-Resistance-management-with-Emerging-Insecticide-Tools.pdf). Pheromone trap captures establish the seasonal starting line (biofix) and gauge local population pressure (moths per trap per week), while heat-unit accumulations (degree days, DD) after the biofix dictate when eggs hatch and when larvicidal or ovicidal sprays must be applied (https://newa.cornell.edu/crop-and-pest-management, https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella). Because modern reduced-risk insecticides target vulnerable eggs or newly hatched neonate larvae before they bore into developing fruit or construct protective tubular leaf shelters, an error of 48 to 72 hours in biofix detection can shift predicted egg-hatch windows outside the period of active residual coverage (https://www.canr.msu.edu/news/dont-trust-the-calendar-why-trapping-matters-during-unusual-weather, https://scholars.unh.edu/cgi/viewcontent.cgi?article=2371&context=thesis).

Degree-Day Calculation Methodology in NEWA

[Measured Result / System Specification] Cornell University's Network for Environment and Weather Applications (NEWA) serves as the foundational decision support system (DSS) across 611+ networked weather stations in the Northeast, Mid-Atlantic, and Midwest (https://rvpadmin.cce.cornell.edu/uploads/doc_778.pdf). Across user evaluations, 99.2% of end users recommend NEWA to farmers (https://rvpadmin.cce.cornell.edu/uploads/doc_400.pdf). Historically, print editions of the Cornell Pest Management Guidelines for Commercial Tree Fruit Production presented the simple Max-Min average formula, $\text{DD} = \frac{T_{\max} + T_{\min}}{2} - T_{\text{base}}$, because growers could compute it rapidly by hand (https://newa.cornell.edu/about-degree-days, https://horticulturalnews.org/105-3/HN1.pdf). In approximately 2006, NEWA transitioned all online insect phenology models to the Baskerville-Emin (BE) single-sine wave algorithm (https://newa.cornell.edu/about-degree-days, https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/hf041613tru161.pdf). The BE formula fits a sinusoidal curve to daily minimum and maximum temperatures and integrates the area above the developmental base threshold ($T_{\text{base}}$), capturing heat units accumulated during warm afternoons in April and May when the daily mean temperature remains below $T_{\text{base}}$ (https://newa.cornell.edu/about-degree-days).

[Measured Result / System Specification] NEWA defines its 24-hour temperature collection window as beginning at 12:01 AM (00:01) and ending at 12:00 AM (24:00 midnight) local station time (https://newa.cornell.edu/about-degree-days). Each of the three target tortricid species operates on a distinct lower developmental threshold ($T_{\text{base}}$) and seasonal accumulation span. For codling moth (CM), NEWA calculates development using a base temperature of 50°F (10.0°C) via the Baskerville-Emin formula (DD50 BE) over a seasonal span of 0 to ~2,000 DD50 from biofix (https://newa.cornell.edu/about-degree-days, https://newa.cornell.edu/crop-and-pest-management, https://barron.extension.wisc.edu/files/2023/02/Codling-Moth.pdf). In the classical Riedl-Croft-Howitt CM simulation model and Trécé/extension tables, an upper developmental cutoff ($T_{\text{upper}}$) of 88°F (31.1°C) (horizontal cutoff: if $T_{\max} > 88^\circ\text{F}$, set $T_{\max} = 88^\circ\text{F}$; if $T_{\min} < 50^\circ\text{F}$, set $T_{\min} = 50^\circ\text{F}$) is specified (https://barron.extension.wisc.edu/files/2023/02/Codling-Moth.pdf, https://scholars.unh.edu/cgi/viewcontent.cgi?article=2371&context=thesis, https://trece.com/wp-content/uploads/PHEROCON-Book.pdf), whereas standard NEWA degree-day tables accumulate Base 50°F BE without an upper cutoff (https://newa.cornell.edu/about-degree-days, https://byfg.org/IPM.pdf). For oriental fruit moth (OFM), NEWA tracks development across three to four generations (0 to ~3,000 DD45 from biofix) using a base temperature of 45°F (7.2°C) (DD45 BE) (https://newa.cornell.edu/about-degree-days, https://newa.cornell.edu/crop-and-pest-management, https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth). While physiological literature specifies an upper threshold of 90°F (32.2°C), NEWA's dedicated OFM tool accumulates Base 45°F BE directly, and Cornell's multi-pest summary tables occasionally cross-tabulate OFM milestones in Base 43°F BE (marked with an asterisk *) or Base 50°F BE for cross-species comparison (https://newa.cornell.edu/crop-and-pest-management, https://blogs.cornell.edu/treefruitpests/uncategorized/2026-weekly-update-17-7-28-2026-anticipating-harvest/). For obliquebanded leafroller (OBLR), NEWA uses a base temperature of 43°F (6.1°C) (DD43 BE) with no upper temperature cutoff across a post-biofix summer span of 0 to ~1,800 DD43 (~2,640 DD43 from January 1) (https://newa.cornell.edu/about-degree-days, https://newa.cornell.edu/crop-and-pest-management, https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/hf080415.pdf, https://byfg.org/IPM.pdf).

Resolving the Biofix Rule Discrepancy (Open Question 1)

[Measured Result / Extension Audit] A recurring source of ambiguity in digital pest-monitoring tools—and a confirmed discrepancy between the UI labels and backend code in the Orchard Sentinel prototype (uploaded:00_ARGON_BRIEF.md)—is whether the biofix for CM, OFM, and OBLR is defined as "first trap catch" or "first sustained trap catch." Tracing primary documentation across NEWA, Cornell Cooperative Extension (CCE), and Penn State Extension reveals why both phrases appear in extension literature and how an automated daily camera trap must reconcile them. On NEWA's web input forms and quickstart training sheets, the user entry field for CM, OFM, and OBLR is labeled "First trap catch" (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella, https://rvpadmin.cce.cornell.edu/uploads/doc_778.pdf, https://blogs.cornell.edu/enychp/tree-fruit/apples/2026-petal-fall-insect-management/). That label is an operational shorthand reflecting the fact that commercial growers and scouts historically inspected traps only once per week (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella). Under a 7-day manual inspection interval, a single stray moth cannot be distinguished temporally from a multi-night flight, so the date of the first positive weekly check (or an estimated mid-week date) is entered into NEWA (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella, https://rvpadmin.cce.cornell.edu/uploads/doc_778.pdf).

When traps are monitored daily—as recommended by extension guides during spring biofix establishment and as performed automatically by Orchard Sentinel—a single early male emerging on an unseasonably warm afternoon is frequently followed by a multi-day cold spell below the dusk mating flight threshold (50–60°F for CM), halting adult activity and egg-laying (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella, https://extension.psu.edu/tree-fruit-insect-pest-codling-moth, https://horticulturalnews.org/105-3/HN1.pdf). Consequently, authoritative entomological guides define the true biological biofix under daily observation as sustained capture. For codling moth (CM), Cornell's official CM Fact Sheet states in its management section that "Degree days, calculated from base 50 F, are accumulated from the date of first sustained moth catch (the biofix)" (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella), and UMass Extension's NEWA 3.0 guide likewise instructs growers that "first you need to enter your first sustained catch of CM in your pheromone traps" (https://www.umass.edu/agriculture-food-environment/fruit/news/newa-30-what-you-need-to-know). Operational extension rules define sustained CM catch as capturing moths on two consecutive warm nights (https://barron.extension.wisc.edu/files/2023/02/Codling-Moth.pdf), whereas Penn State Extension defines CM biofix simply as "when the first adult male codling moth is captured in a sex pheromone trap in the spring" (https://extension.psu.edu/tree-fruit-insect-pest-codling-moth).

For oriental fruit moth (OFM), Penn State Extension explicitly defines biofix as the "first sustained capture of two or more moths per sex pheromone trap" (https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth). Cornell's Hudson Valley Research Lab (HVRL) and statewide tree-fruit reports similarly separate first capture from sustained biofix—for example, recording "Highland-HVRL – First capture: May 6 & Sustained Capture: May 13" and setting the NEWA model biofix on the sustained capture date (https://blogs.cornell.edu/treefruitpests/uncategorized/weekly-report-3-5-13-24/). For obliquebanded leafroller (OBLR), although some Cornell weekly digests use the parenthetical shorthand "Biofix (first trap capture)" (https://blogs.cornell.edu/treefruitpests/uncategorized/7-1-2025/, https://blogs.cornell.edu/enychp/tree-fruit/apples/2026-petal-fall-insect-management/), Cornell's HVRL (Peter Jentsch), UVM Extension, Northeast SARE, and the IPM Institute's Eco-Fruit certification protocol explicitly define OBLR biofix for the NEWA model as first sustained flight / sustained trap catch, defined by Jentsch as capturing moths over two to three successive days (https://blogs.cornell.edu/jentsch/2014/06/08/when-obliquebanded-leafroller-oblr-fly-oblr-management-at-1st-hatch/, https://nyshs.org/wp-content/uploads/2016/10/Obliquebanded-Leafroller-Management-for-Apple-Production-Investigating-Strategies-for-Resistance-management-with-Emerging-Insecticide-Tools.pdf, https://blogs.cornell.edu/jentsch/2020/06/22/rolling-on-obliquebanded-leafroller-emergence-june-21st/, https://blog.uvm.edu/fruit/2016/04/26/updates-to-newa-functions/, https://projects.sare.org/project-reports/one04-017/, https://ipminstitute.org/wp-content/uploads/2026/04/2026-Red-Tomato-Eco-Stone-Fruit-Supplement-v3.5.pdf). Because OBLR 1st-generation adults emerge in early-to-mid June (~884 ± 90 DD43 from Jan 1) when nights are consistently warm, biological first catch and sustained flight usually occur within 24–48 hours of each other—unless an earlier-flying look-alike such as redbanded leafroller (RBLR, Argyrotaenia velutinana, whose 1st flight ends around 753 ± 140 DD43) or spotted fireworm (Choristoneura parallela) enters the trap and triggers a false early biofix (https://blogs.cornell.edu/treefruitpests/uncategorized/2026-weekly-update-10-6-2-2026/, https://www.virginiafruit.ento.vt.edu/oblr.html).

[Measured Result] Relying on regional default biofix dates rather than orchard-specific trap catches introduces substantial timing error. During the 2026 season, Michigan State University Extension documented that the Cornell NEWA model's default estimated biofix was about 10 days later than observed orchard biofixes, whereas the Enviroweather default CM biofix in Sparta was nearly one month earlier than actual first sustained trap captures (https://www.canr.msu.edu/news/dont-trust-the-calendar-why-trapping-matters-during-unusual-weather).

Exact Model Parameters, Thresholds, and Spray Windows by Species

The table below synthesizes the exact numerical parameters from NEWA, Cornell Cooperative Extension, and Penn State Extension across each species' native Baskerville-Emin degree-day scale (0–2,000 DD50 for CM, 0–3,000 DD45 for OFM, and 0–1,800 DD43 post-biofix for OBLR), explicitly separating which management decisions depend on degree days versus weekly trap counts or physical scouting.

Parameter / Decision Stage	Codling Moth (CM, Cydia pomonella)	Oriental Fruit Moth (OFM, Grapholita molesta)	Obliquebanded Leafroller (OBLR, Choristoneura rosaceana)	Primary Source URLs & Citations
Trap Deployment Timing & Canopy Position	Pink to Bloom (~192–249 DD50 from Jan 1). Hang in upper 1/4 to 1/3 of canopy (or 6–8 ft in dwarf trees); \ge 1 trap/5 acres (min 2 traps/block).	Early April to Pink (~222–326 DD43 from Jan 1). Hang at 5–6 ft in outer third of canopy; \ge 2 traps/block.	Petal Fall (~Late May / June 1, ~479 DD43 from Jan 1). Hang at 5–6 ft inside outer canopy. Watch for off-target RBLR catches.	https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella
https://extension.psu.edu/tree-fruit-insect-pest-codling-moth
https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth
https://bl[span_42](start_span)[span_42](end_span)ogs[span_63](start_span)[span_63](end_span).cornell.edu/treefruitpests/uncategorized/2026-weekly-update-10-6-2-2026/
NEWA / Cornell Biofix Rule	First sustained catch (moths on \ge 2 consecutive warm nights) (NEWA UI label: "First trap catch"). Default Jan 1 mean: 475 ± 85 DD43 (249 ± 55 DD50).	First sustained catch (\ge 2 moths/trap across consecutive checks) (NEWA UI label: "First trap catch"). Default: late April (HV) to early May (WNY).	First sustained catch (moths captured over 2–3 successive days) (NEWA UI label: "First trap catch"). Default Jan 1 mean: 884 ± 90 DD43 (523 ± 62 DD50).	https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella
https://www.umass.edu/agriculture-food-environment/fruit/news/newa-30-what-you-need-to-know
https://blogs.cornell.edu/jentsch/2020/06/22/rolling-on-obliquebanded-leafroller-emerge[span_43](start_span)[span_43](end_span)nce-june-21st/
https://blogs.cornell.edu/treefruit[span_57](start_span)[span_57](end_span)pests/uncategorized/weekly-report-3-5-13-24/
https://blogs.cornell.edu/treefruitpests/uncategorized/2026-weekly-update-10-6-2-2026/
Penn State Biofix Rule	First adult male captured in a sex pheromone trap in spring (checked daily until biofix, weekly thereafter).	First sustained capture of \ge 2 moths per sex pheromone trap (checked daily until biofix, weekly thereafter).	First sustained adult flight in late May / early June (preceded by bloom/petal-fall scouting for overwintered larvae).	https://extension.psu.edu/tree-fruit-insect-pest-codling-moth
https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth
https://extension.psu.edu/tree-fruit-insect-pest-obliquebanded-leafr[span_64](start_span)[span_64](end_span)oller
Degree-Day Base (T_{\text{base}}) & Upper Cutoff (T_{\text{upper}})	Base 50°F (10°C) BE sine wave.
Classical/Trécé upper cutoff: 88°F (31.1°C) horizontal (no upper cutoff in standard NEWA tables).	Base 45°F (7.2°C) BE sine wave.
Literature upper cutoff: 90°F (32.2°C) (no upper cutoff in standard NEWA tables).	Base 43°F (6.1°C) BE sine wave.
No upper cutoff in NEWA tables.	https://newa.cornell.edu/about-degree-days
https://newa.cornell.edu/crop-and-pest-management
https://barron.extension.wisc.edu/files/2023/02/Codling-Moth.pdf
https://trece.com/wp-content/uploads/PHEROCON-Book.pdf
Action Threshold (Moths / Trap / Week)	>5 moths/trap/week in standard blocks (PSU, UNH, Rutgers, Cornell); >5 moths/trap/week with 10x lures in mating disruption blocks for supplemental Madex sprays (UW cites 10/trap in low-pressure WI).	>10 moths/trap/week for Generations 1, 2, and 3 (or any visible shoot flagging / fruit entry); >15 moths/trap/week for Generation 4 (September).	No trap count threshold exists. Trap counts establish biofix only. Spray decisions use 3% infested bud clusters/terminals via sequential foliar sampling.	https://extension.psu.edu/tree-fruit-insect-pest-codling-moth
https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth
https://extension.unh.edu/resource/fruit-ipm-reports
https://www.umass.edu/agriculture-food-environment/si[span_65](start_span)[span_65](end_span)tes/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf
https://rvpadmin.cce.cornell.edu/uploads/doc_297.pdf
https://blogs.cornell.edu/treefruitpests/uncategorized/2026-weekly-update-7-5-12-2026-petal-fall-and-warmer-weather/
1st Generation Ovicidal / Early IGR Window	75–100 DD50 (Rimon, Rutgers), 100–150 DD50 (PSU ovicides), or 150–175 DD50 (Cornell ovicides / Intrepid / diamides). Note: Rimon allowed once/season in NYS.	100–150 DD45 (PSU ovicidal products). In apples, Penn State also notes pink stage spray for adult suppression.	Overwintered spring larvae: Scout clusters at bloom/petal fall; spray at Petal Fall if \ge 3\% clusters infested.	https://blogs.cornell.edu/treefruitpests/uncategorized/weekly-report-5-8-2025/
https://extension.psu.edu/tree-fruit-insect-pest-codling-moth
https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth
https://plant-pest-advisory.rutgers.edu/fruit-ipm-updates-week-of-4-27-2026-3-2/
https://ipminstitute.org/wp-content/uploads/2026/04/2026-Red-Tomato-Eco-Stone-Fruit-Supplem[span_66](start_span)[span_66](end_span)ent-v3.5.pdf
1st Generation Larvicidal Window (High / Standard Pressure)	230–250 DD50 (Cornell weekly updates) or 250 DD50 (Cornell Fact Sheet / NEWA, ~3% egg hatch) or 250–350 DD50 (PSU).
2nd cover: 10–14 days later (Cornell) or 14–21 days later / 550 DD50 (~50% hatch; start fruit inspections) if catch >5/trap/wk.	170–200 DD45 (Cornell, ~10–15% hatch around petal fall; PSU peaches 170–195 DD45) and 350–375 DD45 (Cornell Scaffolds & PSU apples/peaches, ~55–60% hatch). Follow-up 10–14 days after petal fall if catch >10/trap/wk.	340–360 DD43 after summer biofix (Cornell CCE/HVRL: 350 DD43; UVM/Eco-Fruit: 360 DD43), targeting 1st summer larval hatch.
2nd cover: 10–14 days later (or after 1.5–2.0 in. rain).	https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella
https://projects.ipmcenters.org/Northeastern/public/ViewProject.cfm?projectID=2352356
https://blogs.cornell.edu/enychp/tree-fruit/apples/scaffolds-podcast-digest-season-4-episode-9-may-26-2026/
https://blogs.cornell.edu/jentsch/2020/06/22/rolling-on-obliquebanded-leafroller-emergence-june-21st/
https://blogs.cornell.edu/treefruitpests/uncategorized/weekly-update-7-21-2025/
1st Generation Low-Pressure Window	360 DD50 after biofix: A single spray is sufficient if pressure is not severe (\le 5 moths/trap/wk and low historical damage).	Covered by standard petal-fall insect complex sprays unless trap catch exceeds 10 moths/trap/wk.	At ~600–650 DD43 after biofix (early July), sample expanding shoot terminals; treat only if \ge 3\% terminals infested.	https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella
https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf
https://nyshs.org/wp-content/uploads/2016/10/Potential-New-Management-Techniques-fo[span_95](start_span)[span_95](end_span)r-Obliquebanded-Leafroller-Large-Plot-Treatments-and-Monitoring-for-Fruit-Damage.pdf
2nd Generation Window & Resistance Rule	Flight starts ~1,000–1,100 DD50. Spray at 1,250–1,300 DD50 (Cornell Fact Sheet/UNH: 1,2[span_45](start_span)[span_45](end_span)60 DD50) if catch >5 moths/trap/wk, plus follow-up at 1,320–1,720 DD50 (10–14 days later) if threshold still exceeded.
Mandatory: Rotate IRAC Mode of Action group from Gen 1.	Early hatch (15–20%): 1,150–1,200 DD45 (Cornell apples / PSU peaches).
Peak hatch (65–72%): 1,450–1,500 DD45 (PSU apples & peaches; UMass). Gated by >10 moths/trap/wk (single spray in apples).
Mandatory: Rotate IRAC group.	2nd flight starts in August (1,400–1,800 GDD / 2,248–2,640 DD43 from Jan 1). In high-population blocks, 1 spray targets hatching 2nd-brood larvae before 3rd-instar winter diapause.
Mandatory: Rotate IRAC group.	https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella
https://blogs.cornell.edu/jentsch/2020/06/22/rolling-on-obliquebanded-leafroller-emergence-june-21st/
https://blogs.cornell.edu/treefruitpests/uncategorized/weekly-update-7-21-2025/
https:[span_108](start_span)[span_108](end_span)//extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth
[span_88](start_span)[span_88](end_span)https://horticulturalnews.org/105-3/HN1.pdf
3rd & 4th Generation Windows	Partial 3rd flight begins around 1,900 DD50 (mid-August); offspring do not overwinter but can cause late fruit pinholes near harvest (monitor PHI).	Gen 3: 2,100–2,200 DD45 (peaches early) and 2,450–2,500 DD45 to 2,900–3,000 DD45 (apples/peaches) if >10 moths/trap/wk.
Gen 4 (Sept): Spray if >15 moths/trap/wk.	None (2 generations per year; 2nd-generation larvae enter diapause in hibernacula on twigs/bark).	https://barron.extension.wisc.edu/files/2023/02/Codling-Moth.pdf
https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth
https://extension.psu.edu/tree-fruit-insect-pest-obliquebanded-leafroller

Which Decisions Depend on Which Numbers (Second-Order Causal Logic)

[Expert Synthesis grounded in Extension Protocols] A naive monitoring interface treats all three lepidopteran species identically by simply displaying a moth count beside a cumulative degree-day total. In commercial orchard practice, however, the causal relationship between trap counts, degree days, and spray execution differs fundamentally across the three species and shifts between spring and summer generations. First, when a pheromone trap captures its initial sustained run of moths (CM, OFM, or OBLR), the biofix date is triggered solely by the presence of sustained flight (1–2+ moths across consecutive checks), regardless of whether the weekly catch total is 2 moths or 40 moths (https://barron.extension.wisc.edu/files/2023/02/Codling-Moth.pdf, https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth). Once the biofix clock starts, degree-day accumulation alone determines when vulnerable eggs or neonate larvae are present, while weekly trap counts or foliar scouting thresholds determine whether the pest population warrants a spray and how many applications are required (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella, https://extension.psu.edu/tree-fruit-insect-pest-codling-moth).

For codling moth (CM), the weekly action threshold of 5 moths/trap/week acts as a branching selector during the first generation (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella, https://extension.psu.edu/tree-fruit-insect-pest-codling-moth, https://extension.unh.edu/resource/fruit-ipm-reports). If weekly captures exceed 5 moths/trap/week (or if the block suffered internal worm damage the previous harvest), the grower must execute a two-spray high-pressure program beginning at 230–250 DD50 (with an optional early ovicide at 150–175 DD50) and following up 10–14 days later (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella, https://blogs.cornell.edu/treefruitpests/uncategorized/weekly-report-5-8-2025/). Penn State Extension specifies that once captures exceed 5 moths/trap/week in an orchard without mating disruption, an insecticide application should be made within 5 to 8 days (and UMass Extension similarly advises preparing for an application within 5 to 7 days) (https://extension.psu.edu/tree-fruit-insect-pest-codling-moth, https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf). Conversely, if first-generation weekly catch remains at or below 5 moths/trap/week in a low-pressure block, the grower skips the 250 DD50 spray and applies a single spray at 360 DD50 (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella, https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf). During the second generation (1,250–1,300 DD50), the 5 moths/trap/week threshold functions as a strict on/off gate to decide whether a second-brood spray (and a 14-day follow-up at 1,320–1,720 DD50) is required (https://extension.psu.edu/tree-fruit-insect-pest-codling-moth, https://horticulturalnews.org/105-3/HN1.pdf).

For oriental fruit moth (OFM), first-generation hatch (170–200 DD45 and 350–375 DD45) in apple blocks generally coincides with routine petal-fall and first-cover sprays targeting plum curculio (https://blogs.cornell.edu/treefruitpests/uncategorized/weekly-update-7-21-2025/). In Generations 2 (1,150–1,200 and 1,450–1,500 DD45) and 3 (2,100–2,500 DD45), however, the degree-day window only indicates when eggs are hatching; the decision to spray is gated by whether weekly trap captures exceed 10 moths/trap/week (or 15 moths/trap/week in September's fourth brood) or whether shoot flagging is observed (https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth, https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf, https://blogs.cornell.edu/treefruitpests/uncategorized/2026-weekly-update-7-5-12-2026-petal-fall-and-warmer-weather/).

For obliquebanded leafroller (OBLR), weekly moth counts after biofix do not gate sprays at all (https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf, https://extension.usu.edu/smallfarms/files/tf-guide.pdf). Field research at Cornell demonstrated that adult male OBLR pheromone trap catches correlate poorly with within-block larval fruit damage because mated females immigrate from surrounding woodlands and alternate rosaceous hosts (https://nyshs.org/wp-content/uploads/2016/10/Obliquebanded-Leafroller-Management-for-Apple-Production-Investigating-Strategies-for-Resistance-management-with-Emerging-Insecticide-Tools.pdf, https://nyshs.org/wp-content/uploads/2016/10/Potential-New-Management-Techniques-for-Obliquebanded-Leafroller-Large-Plot-Treatments-and-Monitoring-for-Fruit-Damage.pdf). Consequently, the dashboard must never display a fabricated "moths/week threshold" for OBLR. Instead, once OBLR biofix is established, the system must count down to 350–360 DD43 (triggering the first summer hatch larvicidal spray in blocks with historical OBLR injury) and 600–650 DD43 (prompting the scout to inspect expanding shoot terminals and fruit clusters against Cornell's 3% larval infestation threshold) (https://blogs.cornell.edu/jentsch/2020/06/22/rolling-on-obliquebanded-leafroller-emergence-june-21st/, https://rvpadmin.cce.cornell.edu/uploads/doc_297.pdf, https://byfg.org/IPM.pdf, https://ipminstitute.org/wp-content/uploads/2026/04/2026-Red-Tomato-Eco-Stone-Fruit-Supplement-v3.5.pdf).

[Measured Result] Weather conditions after application also modify spray timing and chemical choice. Cornell HVRL bioassays proved that when post-treatment temperatures rise from 75°F to 95°F, the toxicity of pyrethroids drops 9.5-fold for lambda-cyhalothrin (Warrior) and 13.6-fold for bifenthrin (Brigade), whereas cold snaps near 40°F reduce larval feeding and lower larval mortality from ingestion-dependent insecticides by 62% (https://nyshs.org/wp-content/uploads/2017/12/Jentsch-Pages-27-32-from-NYFQ-Fall-Book-2017-4.pdf). Furthermore, residual insecticide protection for OBLR and CM normally lasts 10 to 14 days, but is washed off and requires reapplication if 1.5 to 2.0 inches of rainfall occurs (https://blogs.cornell.edu/treefruitpests/uncategorized/weekly-update-7-21-2025/).

2. Competitive Landscape: Screens, Alerts, User Praise, and Complaints

An analysis of the seven primary digital platforms used by tree-fruit growers and IPM consultants—NEWA 3.0, Trapview, Semios, FarmSense, Spensa Z-Trap / DTN Smart Trap, Croptracker, and Agworld—reveals a pronounced market split (https://www.growingproduce.com/nuts/advantages-of-smart-pest-traps-in-your-nut-orchard/, https://wisecrop.com/blog/wisecrop-and-trapview-monitor-to-predict-integrate-to-decide). Automated trap vendors focus on remote insect sensing and flight-curve plotting, whereas farm management systems (FMS) focus on regulatory spray record-keeping and work orders, forcing growers to bridge the gap manually unless direct integrations exist (https://wisecrop.com/blog/wisecrop-and-trapview-monitor-to-predict-integrate-to-decide, https://apps.apple.com/us/app/semios-hub/id6444663759).

Platform-by-Platform Breakdown: Screens, Alerts, Praise, and Complaints

Platform	Sensing & Architecture	Key Screens & Alerts	Measured Metrics & User Praise	Documented Complaints & Field Failure Modes	Primary Source URLs & Citations
NEWA 3.0 (Cornell IPM)	Network of 611+ weather stations (Onset / KestrelMet / airport) driving 40+ online crop/pest models; manual biofix entry.	Screens: Customizable Profile Dashboard, Station Map, 7-day past/forecast DD results table, Pest Stage/Status box, Management Recommendation panel.
Alerts: Risk level badges (Low / Moderate / High).	[Measured Result]: 99.2% of end users recommend NEWA to farmers.
Praise: Free, scientifically trusted land-grant models; NEWA 3.0 profile saves station and biofix dates so users do not re-enter them on every visit.	[Measured Result]: Default biofix estimates erred by ~10 days (MSU 2026) and consistently estimate early green tip / inaccurate petal fall (UMass).
Complaints: NEWA 3.0 UI overhaul required re-learning navigation (9-min tutorial videos needed); historical dates require manually changing "Date of Interest"; no trap photo or spray log storage.	https://www.umass.edu/agriculture-food-environment/fruit/news/newa-30-what-you-need-to-know
https://www.canr.msu.edu/news/dont-trust-the-calendar-why-trapping-matters-during-unusual-weather
https://dev.newa.cornell.edu/blog/the-tools-i-want-where-i-want
https://rvpadmin.cce.cornell.edu/uploads/doc_400.pdf
https://rvpadmin.cce.cornell.edu/uploads/doc_778.pdf
https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/hf061317rea201.pdf
https://rvpadmin.cce.cornell.edu/pdf/lof_newsletter/pdf185_pdf.pdf
Trapview (EFOS)	Solar-powered automated delta/auricular camera trap with 4 cameras, temp/RH sensor, cellular (GPRS/3G/LTE) upload, and optional self-cleaning roll-liner mechanism.	Screens: Regional/farm GIS map, trap image inspector with green bounding boxes on positive target IDs (leaving non-target bycatch unboxed), flight curve & pest stage forecast chart.
Alerts: Real-time threshold & peak flight alerts; API sync to FMS (Wisecrop).	[Measured Result]: FAO deployment of 10 solar traps monitored and reported pests in 80% less time with 80% higher evaluation coverage; H2020 EU report noted one self-cleaning mechanism saved a grower 17 field trips.
Praise: Visual verification via green bounding boxes; local in-trap temp/RH refines plot-level flight curves.	[Measured Result]: Solar panel requires \ge 4 hours/day of full sunlight to stay charged (problematic inside dense upper apple canopies); vendor remote training required for setup.
Complaints: High hardware lease cost; monitoring lives in an isolated app unless integrated via API with a separate farm logbook.	https://trapview.com/crop-solutions/row-crops/
https://u.osu.edu/vegnetnews/2023/04/29/hal-9000-meets-insect-monitoring-introducing-trapview-camera-traps/
https://wisecrop.com/blog/wisecrop-and-trapview-monitor-to-predict-integrate-to-decide
https://cordis.europa.eu/project/id/733979/reporting
https://openknowledge.fao.org/bitstreams/173502bf-3256-4e70-b19d-ab7b001aa0d9/download
Semios (Semios Hub)	Proprietary on-farm wireless mesh network connecting automated camera traps, aerosol mating disruption dispensers, leaf wetness/soil sensors, and frost/irrigation tools.	Screens: Unified farm property map with toggleable data layers, daily trap photo viewer, DD model table, and integrated historical spray records (synced from Agworld or Agrian, added in v0.0.34, April 2025).
Alerts: Configurable trap catch threshold alerts for growers and PCAs.	[Measured Result]: Reports <3% annual customer churn.
Praise: "All-in-one" precision ag-as-a-service; field crew installs/maintains traps and dispensers; recent v0.0.35 update (May 2025) significantly improved mobile load times; combines microclimate data with spray records to assess residual degradation.	[Measured Result]: Semios Hub iOS app had insufficient ratings/reviews to display an aggregate score as of May 2025 (v0.0.35).
Complaints: Closed, high-cost full-service bundle (bundled with mating disruption/irrigation) that is cost-prohibitive for smaller Northeast orchards wanting standalone traps.	https://apps.apple.com/us/app/semios-hub/id6444663759
https://www.uaviq.com/en/2022/03/how-better-data-is-transforming-integrated-pest-management/
https://www.growingproduce.com/nuts/advantages-of-smart-pest-traps-in-your-nut-orchard/
https://www.datamintelligence.com/blogs/top-agricultural-pheromone-companies-integrated-pest-management
FarmSense (FlightSensor)	Patented optical-acoustic sensor inside a non-sticky tunnel trap that classifies insects in real time by wingbeat frequency and optical silhouette; wireless cloud upload.	Screens: Smartphone dashboard showing hourly species-level counts, spatial orchard heatmaps, and downloadable CSV analytics.
Alerts: Custom threshold alerts by specific trap or geographic area.	Praise: Eliminates sticky liner cards and manual messy cleanup; provides hourly real-time flight timestamps rather than once-daily photos; praised by UC Riverside entomologists for near real-time spatial resolution.	Complaints: No photograph of the trapped insect is captured, creating a "black box" verification challenge when growers want visual proof of a biofix moth; commentators note high hardware cost compared to cheap sticky cards where scouts also visually inspect surrounding trees.	https://www.futurefarming.com/smart-farming/tools-data/farmsense-automates-real-time-insect-monitoring/
https://farmsense.io/about-us
https://newatlas.com/good-thinking/farmsense-smart-trap-insects-crops/
https://www.prnewswire.com/news-releases/farmsense-revolutionizes-pest-control-with-next-generation-insect-monitoring-for-farmers-301114813.html
https://farmsense.io/stuck-in-the-past-why-farmers-are-replacing-sticky-traps-with-real-time-insect-monitoring
Spensa Z-Trap / DTN Smart Trap	Z-Trap: Pheromone bucket trap with electrified metal zapper rods that measure bio-impedance upon insect shock.
DTN Smart Trap: Delta-style trap with camera over a 7 \times 7\text{ in.} Alpha Scents sticky insert.	Screens: Mobile/desktop app showing daily/period counts, crop growth stage tracker, pest catalog, and hardware health (signal strength and battery life).
Alerts: Threshold and flight spike notifications.	[Measured Result]: In WinField United apple orchard trials (4–19 acre blocks), Z-Trap counts were within 80% of manual checks, kept users logged in, and had a good pest catalog. In Auburn trials (2017–2018), DTN Smart Trap photo quality, battery life, and multi-location archiving were rated outstanding.	[Measured Result]: In WinField trials, Z-Trap could only identify one insect at a time, missed small/beneficial insects, and was unreliable in corn (false positives from plant debris hitting zapper rods and false negatives for CEW). In Auburn trials, DTN Smart Trap sticky bottoms filled up quickly during peak moth activity, requiring frequent manual visits, and all traps required physical checks after heavy rain/storms.	https://www.winfieldunited.com/news-and-insights/z-trap-system
https://www.aces.edu/blog/topics/farming/modern-insect-pest-monitoring-using-automatic-traps/
https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.pdf
Croptracker	Cloud & mobile (iOS/Android/iPad) specialty-crop Farm Management Software (FMS) focused on spray records, harvest/bin tracking, and GAP compliance.	Screens: Farm block map, Spray module, Harvest/cooler inventory, Employee time-clock, and one-click Food Safety / GAP Audit Report generator.	[Measured Result]: 4.8/5 on G2 (11 reviews; 9.8/10 Meets Requirements, 9.7/10 Ease of Use, 9.3/10 Support) and 4.5/5 on Capterra (28 reviews).
Praise: Extracts chemical spray and disease records in under a minute for audits (CanadaGAP/GlobalG.A.P.); easy error correction; strong field mapping.	[Measured Result / Verified Reviews]: Reviewers complain about: (1) rotary time-picker dials that older workers struggle to wind (preferring direct number keypad entry); (2) inability to scan in direct sunlight; (3) sluggish page switching on slow internet; (4) inconsistent 12-hr vs. 24-hr clocks; (5) lack of chemical inventory tracking and slower event input than legacy tools; (6) complex initial field setup.	https://www.capterra.com/p/152378/CropTracker/reviews/
https://www.g2.com/products/croptracker/reviews
https://www.capterra.com/p/152378/CropTracker/
https://www.g2.com/compare/croptracker-vs-granular
https://www.g2.com/compare/conservis-vs-croptracker
Agworld	Collaborative multi-role platform connecting growers, agronomists/consultants, and applicators for scouting, prescriptions (Rx), work orders, and cost tracking.	Screens: iPhone/iPad offline-capable Scouting app, Agronomist Recommendation/Prescription (Rx) builder, Work Order converter, and per-block Cost/Profitability ledger.	[Measured Result]: 4.5/5 on Capterra (44 reviews; 95% positive; Crop Management rated 4.8/5).
Praise: Best-in-class consultant-to-grower collaboration; turns in-field scouting observations directly into spray work orders and tracks cost of production on mobile without going to an office.	[Measured Result]: Pricing starts at $1,495.00/year (and up to $1,495/user/month for enterprise tiers).
Complaints: High cost for smaller or marginal growers (who request longer free trials or discounts); precision layer/Rx tools historically felt "clunky" before recent updates.	https://www.capterra.com/p/173867/Agworld/pricing/
https://www.capterra.com/p/173867/Agworld/
https://www.capterra.com/p/265826/MyCrops/
https://www.g2.com/products/agworld/reviews

Second-Order Insights from Platform Evaluations

[Expert Synthesis] Cross-referencing extension field trials from Ohio State University, the University of Minnesota, Auburn University, and WinField United with verified grower software reviews yields four structural design lessons for Orchard Sentinel. First, non-visual insect sensors struggle to maintain grower confidence when counts diverge from expectations. Although optical-acoustic (FarmSense) and bio-impedance zapper (Z-Trap) traps eliminate messy sticky liners, WinField United's field tests demonstrated that plant debris triggers false positives on zapper rods, and University of Minnesota Extension noted that discrepancies between automated traps and traditional traps shift apparent peak flight dates and downstream scouting recommendations (https://blog-crop-news.extension.umn.edu/2026/07/can-ai-improve-insect-monitoring.html, https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.pdf, https://www.winfieldunited.com/news-and-insights/z-trap-system). Conversely, Auburn University's multi-year evaluation of camera-based traps (DTN Smart Trap) concluded that outstanding photograph quality is the primary driver of user trust, because "photos allow easy verification of total numbers in a trapping period" (https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.pdf).

Second, Ohio State University Extension's orchard deployment of Trapview validated a highly intuitive visual convention: the trap image displays all insects on the glue, but draws bright green bounding boxes only around positively identified target pests, leaving non-target bycatch unboxed (https://u.osu.edu/vegnetnews/2023/04/29/hal-9000-meets-insect-monitoring-introducing-trapview-camera-traps/). This immediately reassures the grower or scout that the computer vision pipeline detected the non-target flies or leafrollers on the card and deliberately excluded them from the target pest count. Third, Auburn University documented that automated sticky-card traps fill up rapidly during peak moth flights, causing overlapping specimens and undercounting if the dashboard fails to track liner saturation and alert the scout to swap the card, while severe rainstorms and wind events require physical trap checks regardless of automation (https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.pdf). Fourth, as both Wisecrop and Semios (in its April 2025 v0.0.34 Agworld/Agrian spray record integration) recognized, trap monitoring loses value when isolated from field operations (https://wisecrop.com/blog/wisecrop-and-trapview-monitor-to-predict-integrate-to-decide, https://apps.apple.com/us/app/semios-hub/id6444663759). Plotting historical spray application dates and rainfall directly onto the pest flight and degree-day chart allows the grower to see whether an insecticide application suppressed adult flight and exactly when the 10-to-14-day residual window expires (https://www.uaviq.com/en/2022/03/how-better-data-is-transforming-integrated-pest-management/).

3. Farmer Usability, Trust in Automated Counts, and Regulatory Spray Record-Keeping

Field Ergonomics: Phone-First, Low Signal, Sunlight, and Gloves

[Measured Result & User Review Evidence] Commercial fruit growers and farm managers rarely sit at desktop workstations during the May–August growing season; they check pest status on smartphones or iPads from pickup trucks, tractor cabs, or packing house loading bays (uploaded:00_ARGON_BRIEF.md, https://www.capterra.com/p/152378/CropTracker/, https://www.capterra.com/p/173867/Agworld/). Verified Capterra and G2 reviews of Croptracker and Semios Hub expose the exact user-interface anti-patterns that fail in orchard environments. Apple growers explicitly complained in Capterra reviews about mobile interfaces failing in bright outdoor sunlight ("not been able to scan fruit in sun (any sun). As i dont have many load bays that have the shade...") (https://www.capterra.com/p/152378/CropTracker/). Consequently, the Orchard Sentinel dashboard must default to a high-contrast light theme (#FFFFF[span_184](start_span)[span_184](end_span)F background, #111111 near-black typography, $\ge 7:1$ AAA contrast ratio, and bold bordered status pills) rather than low-contrast dark mode or muted pastel grays that wash out in direct orchard sun.

Physical input ergonomics are equally critical for gloved or older hands. A verified Capterra reviewer overseeing orchard crews noted that rotary time-picker wheels caused constant friction: "The dials when clocking in times. Seeing a lot of the older guys struggle to use that, perhaps keeping to punching in numbers rather than winding a dial would be more ideal and more efficient" (https://www.capterra.com/p/152378/CropTracker/), while another reviewer criticized inconsistent switching between 12-hour and 24-hour clocks (https:/[span_185](start_span)[span_185](end_span)/www.capterra.com/p/152378/CropTracker/). All interactive touch targets in Orchard Sentinel (buttons, trap cards, review queue confirm/reject actions) must therefore measure at least $48 \times 48\text{ px}$ with $8\text{ px}$ spacing for gloved thumbs; numeric or date inputs must invoke native numeric keypads (inputmode="numeric") or single-tap preset buttons ("Today", "Yesterday") rather than scrollable drum dials; and all timestamps must consistently render in local 12-hour AM/PM format (America/New_York). Furthermore, G2 reviewers cited "occasional sluggishness with slow internet" and "a little slow to switch between pages" as primary drawbacks of cloud farm apps, while Semios Hub prioritized load-time reductions in its May 2025 mobile update (https://apps.apple.com/us/app/semios-hub/id6444663759, https://www.capterra.com/p/152378/CropTracker/, https://www.g2.com/compare/croptracker-vs-granular). WinField United also praised the Z-Trap app specifically because it kept the user logged in across sessions (https://www.winfieldunited.com/news-and-insights/z-trap-system). Orchard Sentinel's server-rendered Jinja2 HTML is naturally lightweight, but its overview screen must never load full-resolution ($3\text{ MP}$–$5\text{ MP}$) trap JPEGs. Keeping the first screen to pure HTML/CSS/SVG under $40[span_172](start_span)[span_172](end_span)\text{ KB}$, backed by persistent 90-day session cookies and a basic Service Worker that caches the most recent "What to Do This Week" summary for offline viewing, ensures instant operation in dead-zone orchard blocks (uploaded:00_ARGON_BRIEF.md).

Checking Cadence and Notification Channels (SMS vs. Email vs. Push)

[Measured Result / Extension Protocol] Grower checking cadence follows a bimodal seasonal schedule dictated by extension guidelines (https://extension.psu.edu/tree-fruit-insect-pest-codling-moth, https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth, https://www.canr.msu.edu/news/dont-trust-the-calendar-why-trapping-matters-during-unusual-weather). During the Pre-Biofix Phase (April to mid-June), extension guides instruct checking traps daily—especially after warm, calm evenings above $50–60^\circ\text{F}$—to capture the exact biofix date for OFM, CM, and OBLR (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella, https://extension.psu.edu/tree-fruit-insect-pest-codling-moth, https://extension.psu.edu/tree-fruit-insect-pest-oriental-fruit-moth, https://cropsandsoils.extension.wisc.edu/june-12th-2025-weather-outlook/). During the Post-Biofix Phase (Mid-May through Harvest), once biofix is locked in, growers check trap counts once per week to compare weekly captures against action thresholds (5/wk for CM, 10/wk for OFM) and monitor degree-day progress toward spray windows (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella, https://extension.psu.edu/tree-fruit-insect-pest-codling-moth, https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf).

[Expert Synthesis on Notification Channels] Because orchard blocks frequently lack reliable 4G/5G data for web push notifications and growers typically read long-form emails (such as Cornell's weekly pest updates) at an office desk once a week, notification channels must be tiered by urgency and bandwidth. SMS (Text Message via Twilio or carrier email-to-SMS gateway) should be reserved strictly for high-urgency event triggers because SMS transmits over a single bar of 2G/LTE control channel in a tractor cab and commands a near-100% open rate. Specifically, SMS alerts should fire on four events: (1) Biofix Triggered or Candidate Detected (e.g., "Orchard Sentinel [Block A]: CM Sustained Biofix reached May 16 (3 moths over 2 nights). 1st hatch spray window (230-250 DD50) projected May 28"); (2) Spray Window Imminent (48–72 Hours Out) or Open (e.g., "Orchard Sentinel [Block A]: CM at 218 DD50. Spray window (230-250 DD50) opens in ~2 days (May 28). Weekly catch: 7 moths/trap (ABOVE 5/wk threshold)"); (3) Action Threshold Exceeded (e.g., "Orchard Sentinel [Block B]: OFM catch hit 14 moths/trap this week (Threshold: 10/wk) at 1,420 DD45. Spray recommended"); and (4) Critical Hardware or Liner Failure (e.g., "Orchard Sentinel [Hub 1 / Trap 3]: Hub offline >12 hrs" or "Trap 3 liner 70% covered with debris—replace card") (uploaded:00_ARGON_BRIEF.md, https://www.growingproduce.com/nuts/advantages-of-smart-pest-traps-in-your-nut-orchard/, https://newatlas.com/good-thinking/farmsense-smart-trap-insects-crops/, https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.pdf). Email should be used for a scheduled Weekly Monday Morning Digest (6:00 AM)—matching the familiar Monday morning cadence of Cornell's HVRL and Scaffolds digests (https://blogs.cornell.edu/jentsch/2014/06/08/when-obliquebanded-leafroller-oblr-fly-oblr-management-at-1st-hatch/)—containing a full summary table of all blocks, current and 7-day forecasted DD accumulations, weekly trap counts, thumbnail crops of newly detected moths, and battery/liner health. Web Push should be avoided in Version 1 because it requires Progressive Web App (PWA) home-screen installation, browser permission prompts, and active cellular data connectivity.

Building and Losing Grower Trust in Automatic Counts (Open Question 10)

[Measured Result & Domain Analysis] Understanding why growers stop trusting automatic insect counts—and what they are willing to pay—is essential for product survival. Growers lose trust in automated counts through three primary failure mechanisms. First, unverified false positives from look-alike tortricids corrupt the biofix clock. Pheromone lures are not 100% selective (uploaded:00_ARGON_BRIEF.md): Cornell Extension explicitly warns that Redbanded Leafroller (RBLR, Argyrotaenia velutinana) is frequently captured in OBLR traps (https://blogs.cornell.edu/treefruitpests/uncategorized/2026-weekly-update-10-6-2-2026/), Virginia Tech Extension notes that Spotted Fireworm (Choristoneura parallela) enters leafroller traps (https://www.virginiafruit.ento.vt.edu/oblr.html), and Penn State and Cornell note that Lesser Appleworm (LAW, Grapholita prunivora) and Oriental Fruit Moth (OFM) overlap in appearance and injury with Codling Moth (CM) (https://nyshs.org/wp-content/uploads/2016/10/Obliquebanded-Leafroller-Management-for-Apple-Production-Investigating-Strategies-for-Resistance-management-with-Emerging-Insecticide-Tools.pdf, https://extension.psu.edu/insects-pests-and-diseases/pest-disease-and-weed-identification/insect-identification-and-control?p=7). If an unreviewed AI error classifies an early May RBLR as OBLR or a sap beetle/blowfly as CM, the software sets a bogus biofix 2 to 3 weeks early, shifting all spray windows (https://blog-crop-news.extension.umn.edu/2026/07/can-ai-improve-insect-monitoring.html). Second, silent liner replacement or double-counting of shifted moths inflates weekly catch totals above the 5 moths/trap/week threshold and triggers an unnecessary $40–$80/acre spray (uploaded:00_ARGON_BRIEF.md). Third, silent hardware or weather failures—such as LED glare blowing out 10–13% of the card (uploaded:00_ARGON_BRIEF.md), storms knocking a trap askew (https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.pdf), or a camera node dropping offline for 4 days during biofix week while the dashboard displays "0 moths caught (Safe)" instead of "Camera Offline — Unknown Risk"—destroy grower confidence if fruit damage appears at harvest.

To build durable trust, the dashboard must implement three transparency mechanisms. First, following the Trapview and DTN Smart Trap best practice validated by Ohio State and Auburn Extension (https://u.osu.edu/vegnetnews/2023/04/29/hal-9000-meets-insect-monitoring-introducing-trapview-camera-traps/, https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.pdf), every count on the dashboard must be one tap away from the actual sticky-card photo with color-coded bounding boxes: a Solid Green Box for human-verified target pests (CM, OFM, OBLR), a Dashed Amber Box for unverified AI target predictions (with confidence percentage), and a Muted Gray Box for excluded non-targets (other_moth, other_insect, debris). Second, the photo inspector and review queue should display a pinned visual reference strip stating the exact diagnostic traits and millimeter scale from Cornell and Penn State fact sheets: CM measures $10–12\text{ mm}$ in body length ($15–20\text{ mm}$ wingspan) and is iridescent gray-brown with a chocolate-brown/copper-gold patch at each forewing tip (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella); OFM is smaller ($6–8\text{ mm}$ body, $\sim 12\text{ mm}$ wingspan) and mottled gray-brown without the bronzed wingtip patch (uploaded:00_ARGON_BRIEF.md, https://extension.psu.edu/insects-pests-and-diseases/pest-disease-and-weed-identification/insect-identification-and-control?p=6); and OBLR is much larger ($19–25\text{ mm}$ body, $25\text{ mm}$ / $1\text{ in.}$ wingspan) with light reddish-brown forewings crossed by three oblique chocolate-brown bands (https://extension.psu.edu/tree-fruit-insect-pest-obliquebanded-leafroller, https://www.virginiafruit.ento.vt.edu/oblr.html). Third, the UI must never allow an unreviewed AI prediction to silently set a biofix; every biofix date must carry an explicit verification badge ("Biofix: May 16 (Verified by Scout)" vs. "Pending Verification — Tap to Confirm Photo").

[Measured Benchmarks & Economic Willingness-to-Pay] Commercial pheromone and smart-trap vendors (Suterra, Semios, Trapview) face adoption resistance when upfront hardware or subscription costs outstrip manual scouting costs (https://www.datamintelligence.com/blogs/top-agricultural-pheromone-companies-integrated-pest-management, https://newatlas.com/good-thinking/farmsense-smart-trap-insects-crops/). Auburn Extension notes that commercial automatic traps are expensive and primarily cost-effective for larger farms (https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.[span_47](start_span)[span_47](end_span)pdf), while software reviewers on G2 praise Croptracker as affordable compared to enterprise platforms like Granular or Agworld ($1,495/year starting price) (`https://www.capterra.com/p/173867/Agworld/pricing/`, `https://www.g2.com/compare/croptracker-vs-granular`)[span_231](start_span)[span_231](end_span)[span_232](start_span)[span_232](end_span). A manual delta trap and lures cost $\sim \$15–\$25/\text{season}$, plus $\sim 15\text{ minutes/week}$ of [span_179](start_span)[span_179](end_span)labor over 18 weeks ($\sim 4.5\text{ hours} \times $20/\text{hr} = $90/\text{trap/season}$, or up to 17 saved field trips per trap as documented in the EU H2020 Trapview report (`https://cordis.europa.eu/project/id/733979/reporting`)). Eliminating even **one unnecessary cover spray** on a 10-acre block saves $\$400–\$800$ in chemical, fuel, and labor. Consistent with the project brief's constraint that *"a few hundred dollars of hardware per trap is already too much"* (`uploaded:00_ARGON_BRIEF.md`), Northeast growers will realistically pay **$$50–$100/\text{trap/year}$** in total service fees or **$$80–$150$ outright for owned low-cost hardware (amortized over 3 seasons to $<\$50/\text{yr}$), with the web dashboard included at no extra per-seat fee.

Spray Record-Keeping and Audit Compliance Requirements

[Measured Result / Legal & Regulatory Mandate] When a pest-monitoring dashboard recommends an insecticide spray—or recommends holding off because counts are below threshold—that decision feeds directly into two sets of mandatory legal and buyer audit records in New York and the Northeast: New York State DEC regulations (Title 6 NYCRR Part 325.25 and the Pesticide Reporting Law, ECL Article 33 Title 12), Federal EPA Worker Protection Standard (WPS) rules, and Eco-Apple / GAP buyer certification audits (https://www.nysprl.com/PRLRecordkeepingRequirementsforApplicators.pdf, https://www.law.cornell.edu/regulations/new-york/6-NYCRR-325.25, https://ipminstitute.org/wp-content/uploads/2026/04/2026-Red-Tomato-Eco-Stone-Fruit-Supplement-v3.5.pdf). Under 6 NYCRR § 325.25, every certified commercial applicator, commercial technician, and certified private applicator (grower) in New York must maintain daily pesticide use records for a minimum of 3 years (https://www.nysprl.com/PRLRecordkeepingRequirementsforApplicators.pdf, https://www.docsity.com/en/docs/new-york-commercial-pesticide-applicator-category-7g-cooling-towers-certification-exam-e/20241342/). Commercial applicators and technicians must file an electronic annual report with NYSDEC by February 1 each year (registered pesticide businesses by January 15), even if zero applications were made (https://www.nysprl.com/PRLRecordkeepingRequirementsforApplicators.pdf, https://treatlog.com/resources/ny-electronic-prl, https://www.nysprl.com/PRLReportingRequirementsforApplicators.pdf). Private applicators (growers applying to their own orchards) do not submit the February 1 annual report, but must retain on-farm daily application records for 3 years under ECL 1205(2)(b) and 6 NYCRR 325.25(d), plus 2 years of employee safety and Safety Data Sheet (SDS) records under the federal WPS (https://www.nysprl.com/PRLRecordkeepingRequirementsforApplicators.pdf, https://www.nysprl.com/PRLReportingRequirementsforApplicators.pdf, https://extapps.dec.ny.gov/docs/materials_minerals_pdf/privatercdfr.pdf).

NYSDEC enforcement orders (6 NYCRR § 325.25(a)) and the official NYSDEC Recordkeeping for WPS and Private Applicators Form (privatercdfr.pdf) establish that omitting target organism, dosage rate, method of application, or specific place of application is a finable violation, and all required fields must be recorded before leaving the application site (https://extapps.dec.ny.gov/docs/regions_pdf/williamsheaord.pdf, https://extapps.dec.ny.gov/docs/materials_minerals_pdf/pestchecklist.pdf, https://extapps.dec.ny.gov/docs/materials_minerals_pdf/privatercdfr.pdf). Simultaneously, under the IPM Institute's Red Tomato Eco Fruit protocol, third-party auditors verify why a spray was applied by requiring that systematic sampling results, biofix dates, degree-day calculations, and weekly trap counts be documented in scouting reports whenever a grower treats for OBLR or internal worms (https://ipminstitute.org/wp-content/uploads/2026/04/2026-Red-Tomato-Eco-Stone-Fruit-Supplement-v3.5.pdf). Orchard Sentinel does not need to replicate a full accounting ERP like Agworld or Granular (https://www.g2.com/compare/croptracker-vs-granular), but providing a lightweight "Log Spray / Export IPM Justification Report" table that stamps the trap's phenology and count data alongside the NYSDEC/WPS spray fields turns the dashboard into a one-click compliance tool.

Regulatory / Audit Field	Legal Mandate (NYSDEC 6 NYCRR 325.25 / WPS / Eco-Fruit)	Exact Formatting & Orchard Sentinel Auto-Fill Rule	Primary Source URLs & Citations
1. EPA Registration Number & Product Name	Mandatory for all applications under 6 NYCRR 325.25 & WPS (or active ingredient for FIFRA 25(b) Minimum Risk products).	User selects from pre-populated NY tree-fruit insecticide dropdown (auto-fills EPA Reg. No., active ingredient, and IRAC Mode of Action Group to check resistance rotation).	https://www.nysprl.com/PRLRecordkeepingRequirementsforApplicators.pdf
https://dec.ny.gov/regulatory/regulations/policy-dshm-pes-05-10-compliance-with-the-pesti[span_103](start_span)[span_103](end_span)cide-reporting-law
https://extapps.dec.ny.gov/docs/materials_minerals_pdf/privatercdfr.pdf
2. Target Organism (Pest) & Crop Treated	Mandatory under 6 NYCRR 325.25(a) (omission cited in DEC enforcement orders).	Auto-filled by Orchard Sentinel from the block and trap species (e.g., Codling Moth (Cydia pomonella) — Apple, Honeycrisp).	https://www.law.cornell.edu/regulations/new-york/6-NYCRR-325.25
https://extapps.dec.ny.gov/docs/regions_pdf/williamsheaord.pdf
3. Place of Application & Acres Treated	Street address, county, municipality, 5-digit ZIP code, specific block/field name or map, and # of Acres Treated.	Auto-filled by Orchard Sentinel from the Farm & Block profile (Address, County, Municipality, 5-digit ZIP, Block Name, Acreage).	https://www.nysprl.com/PRLRecordkeepingRequirementsforApplicators.pdf
https://treatlog.com/resources/ny-elect[span_248](start_span)[span_248](end_span)ronic-prl
https://extapps.dec.ny.gov/docs/materials_minerals_pdf/privatercdfr.pdf
4. Undiluted Quantity Used & Dosage Rate	Must record total undiluted product quantity (e.g., 500 fl oz, NOT 1,000 gal tank mix) plus label mixing Dosage Rate (0.5 fl oz/gal or 6 oz/A).	User enters Dosage Rate; Orchard Sentinel multiplies Dosage Rate × Block Acres to auto-calculate Total Undiluted Product Used.	https://www.nysprl.com/PRLRecordkeepingRequirementsforApplicators.pdf
https://extapps.dec.ny.gov/docs/materials_minerals_pdf/privat[span_249](start_span)[span_249](end_span)ercdfr.pdf
5. Date, Time & Method of Application	Date and start/end time (MM/DD/Time) plus equipment method (e.g., Airblast sprayer).	Defaults to current date/time in 12-hour America/New_York format and default method (Airblast sprayer).	https://www.nysprl.com/PRLRecordkeepingRequirementsforApplicators.pdf
https://extapps.dec.ny.gov/docs/regions_pdf/williamsheaord.pdf
http[span_250](start_span)[span_250](end_span)s:[span_260](start_span)[span_260](end_span)//extapps.dec.ny.gov/docs/materials_minerals_pdf/privatercdfr.pdf
6. Applicator Name & Certification #	Certified Applicator/Technician name and 8-character NYSDEC Certification ID (plus supervising applicator if apprentice).	Saved once in Farm Settings profile; auto-stamped on every logged spray.	https://www.nysprl.com/PRLRecordkeepingRequirementsforApplicators.pdf
https://spraydocs.com/ny
7. WPS Safety, REI, PHI & Weather	Restricted Entry Interval (REI) hours & expiration timestamp; Pre-Harvest Interval (PHI); Wind Speed/Direction & AEZ distance (for RUPs).	Auto-calculates REI expiration timestamp (Application End Time + REI hours) and pulls local wind speed/direction from the linked NEWA station.	https://ccefm.com/viewprogram.asp?progID=5
https://extapps.dec.ny.gov/docs/materials_minerals_pdf/privatercdfr.pdf
8. IPM Justification (Biofix, DD & Trap Count)	Mandatory for Eco-Apple / Red Tomato / GAP audits to prove sprays were triggered by thresholds and DD models.	Auto-stamped by Orchard Sentinel: Records Active Biofix Date, Accumulated DD at Spray, Weekly Trap Catch (Avg/High), 3% Scouting Result, and Verified Capture Photo UID.	https://ipminstitute.org/wp-content/uploads/2026/04/2026-Red-Tomato-Eco-Stone-Fruit-Supplement-v3.5.pdf

4. Multi-Farm, Scout, and IPM Consultant Requirements

[Measured Result & Workflow Analysis] While an individual owner-operator manages 1 to 3 farms partitioned into 5 to 30 cultivar blocks, an independent IPM consultant, cooperative extension specialist, or dealer scout oversees 10 to 50+ client farms (hundreds of traps) across multiple counties (uploaded:00_ARGON_BRIEF.md, https://trapview.com/crop-solutions/row-crops/, https://www.capterra.com/p/173867/Agworld/). Extension guidelines mandate a minimum trap density of 1 trap per 5 acres with at least 2 traps per block for codling moth (https://extension.psu.edu/tree-fruit-insect-pest-codling-moth), meaning a single 100-acre apple orchard operates 20+ CM traps alongside OFM and OBLR traps. Serving both individual growers and multi-farm consultants without duplicating the codebase requires a three-level spatial hierarchy (Farm $\rightarrow$ Block $\rightarrow$ Trap) with intelligent block-level aggregation. Because growers apply sprays to blocks (e.g., "Home Farm — Block 4 Honeycrisp, 12 acres") rather than individual trees (https://www.winfieldunited.com/news-and-insights/z-trap-system, https://www.capterra.com/p/152378/CropTracker/), the block view must aggregate multiple traps of the same species by locking the block's default biofix to the earliest confirmed sustained-catch biofix among its traps, while displaying both the block average and the block high (maximum) weekly trap count side-by-side—mirroring the exact Avg and High reporting format used in Rutgers Extension's regional IPM tables (https://plant-pest-advisory.rutgers.edu/fruit-ipm-updates-week-of-4-27-2026-3-2/)—so a border hot-spot trap exceeding 5 moths/trap/week is never masked by an interior trap catching zero.

For the multi-farm scout or consultant logging in at 6:00 AM, clicking through 30 separate farm pages is unworkable. The consultant's top-level landing view must render a Cross-Farm Triage Portfolio Table sorted strictly by exception urgency: first, any unverified Biofix Candidates awaiting photo confirmation in the Review Queue; second, blocks across all client farms currently inside an active Spray Window (Red); third, blocks projected to enter a Spray Window within 72 hours (Amber); and fourth, traps requiring physical field maintenance (Liner > 60% covered, Lure > [span_67](start_span)[span_67](end_span)28–42 days old, Battery < 3.5V, or Node missed >= 2 check-ins). In the Review Queue, grouping cropped insect tracks by predicted species (CM, OFM, OBLR, other_moth) and binding single-keystroke shortcuts (1=CM, 2=OFM, 3=OBLR, 4=Other Moth, 5=Other Insect, 6=Debris, Space=Confirm AI prediction) allows a scout or student team member to confirm 100 detections across 15 farms in under 3 minutes (uploaded:00_ARGON_BRIEF.md).

Finally, multi-farm collaboration requires frictionless role-based sharing and physical maintenance routing. Growers frequently want their private crop advisor, extension specialist, or custom applicator to view block counts and confirm insect IDs without sharing a master administrator password (https://trapview.com/crop-solutions/row-crops/, https://www.capterra.com/p/173867/Agworld/). Supporting three lightweight permission roles—Grower (Farm Owner/Editor), Scout/Consultant (Multi-Farm Reviewer & Recommender), and Read-Only Viewer (Shareable Token Magic Link per Farm)—eliminates account-setup friction. Because sticky liners must be replaced every 1 to 4 weeks (or immediately after cleaning/resetting following a peak flight or threshold spray (https://blogs.cornell.edu/treefruitpests/uncategorized/7-1-2025/, https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._26_no._15_july_17_2018.pdf, https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.pdf)) and pheromone lures must be refreshed at the start of the second-generation flight (~1,000–1,583 DD50 for CM, typically every 4–6 weeks) (https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._26_no._15_july_17_2018.pdf), a printable "Scout Field Route Checklist" that filters across all farms for only those specific traps needing a new liner, new lure, or battery swap saves hours of unnecessary orchard walking (https://cordis.europa.eu/project/id/733979/reporting).

5. Actionable Dashboard Recommendations, V1 Page-by-Page Spec, and Exact Wording

Architectural & Codebase Findings for Orchard Sentinel (Section 4 Format)

To align the existing Orchard Sentinel backend (server/sentinel_server/) with Northeast extension rules before deploying the new dashboard screens, the student team should address four high-priority domain findings (uploaded:00_ARGON_BRIEF.md):

DOC-01 · Unify OBLR biofix rule and expose dual First-Catch / Sustained-Catch dates

⚬ Severity: high     Confidence: Sure     Effort: S

⚬ Where: server/sentinel_server/phenology.py and dashboard templates (server/sentinel_server/templates/)

⚬ Evidence: Brief Section 3: "the OBLR biofix label and the code disagree" and Open Question 1: "OBLR biofix: NEWA's rule (first catch, or first sustained catch?)"

⚬ What goes wrong: When the UI label says "First catch" (matching NEWA's form label) while the backend code requires sustained catch (or vice versa), a single early straggler moth or misclassified RBLR (Argyrotaenia velutinana) either triggers a premature biofix 2–3 weeks early or leaves the grower wondering why a visible moth on the card did not start the degree-day clock.

⚬ Fix: Standardize all three species (CM, OFM, OBLR) in phenology.py to compute both first_catch_date ($\ge 1$ verified target moth) and sustained_biofix_date (verified target moths caught on $\ge 2$ consecutive local calendar days, or $\ge 2$ target moths within a 48-hour window, dated to the first day of that sequence). Default active_biofix_date to sustained_biofix_date, display both dates clearly in the UI ("1st Catch: May 12 | Sustained Biofix: May 15 [Active]"), and add a POST /blocks/{id}/biofix-override endpoint so the grower or scout can manually lock any date.

SRV-01 · Prevent unverified AI predictions from auto-triggering season biofix

⚬ Severity: critical     Confidence: Sure     Effort: S

⚬ Where: server/sentinel_server/pipeline/worker.py and server/sentinel_server/phenology.py

⚬ Evidence: Brief Section 1: "Getting the biofix date right, to within a day, matters more than counting every moth perfectly" and Section A3: "can one wrong unreviewed label move the biofix?"

⚬ What goes wrong: Before a pest's seasonal biofix is locked, if the classifier labels a non-target look-alike (RBLR, LAW, sap beetle, or bark debris) as CM, OFM, or OBLR with high confidence (taking the 9-in-10 unreviewed path), phenology.py automatically sets the seasonal biofix and shifts all downstream spray windows (250 DD50, 350 DD43).

⚬ Fix: In worker.py, force 100% of target-species tracks (CM, OFM, OBLR) detected prior to a trap's confirmed seasonal biofix into the human review_queue with priority="CRITICAL_BIOFIX_CANDIDATE", regardless of classifier confidence. In phenology.[span_50](start_span)[span_50](end_span)[span_52](start_span)[span_52](end_span)py, compute automatic sustained_biofix_date using only human_verified=True tracks (while showing a yellow banner: "Pending Biofix Candidate on May 14 — 1 tap to verify photo").

SRV-02 · Convert naive UTC timestamps to America/New_York before slicing NEWA daily degree days and night flights

⚬ Severity: high     Confidence: Sure     Effort: S

⚬ Where: server/sentinel_server/phenology.py and server/sentinel_server/services.py

⚬ Evidence: Brief Section A1: "time and timezone errors (naive UTC is stored; local dates for biofix)" and NEWA documentation: "In NEWA, midnight marks the end of the day. NEWA's 24-hour period runs from 12:01 AM (= 0:01) until 12 AM (midnight)" (https://newa.cornell.edu/about-degree-days)

⚬ What goes wrong: Codling moths and leafrollers fly and mate at dusk (7:00 PM–11:00 PM EDT, which is 23:00–03:00 UTC the next day) (https://cals.cornell.edu/integrated-pest-management/outreach-education/fact-sheets/codling-moth-cydia-pomonella). Slicing naive UTC dates assigns evening captures to the following calendar day and misaligns daily $T_{\max}/T_{\min}$ windows against NEWA's 00:01–24:00 local midnight boundary.

⚬ Fix: Convert all capture timestamps and sensor readings via zoneinfo.ZoneInfo("America/New_York") prior to assigning capture dates or computing daily Baskerville-Emin degree days. Additionally, assign any night-flight capture between 18:00 and 06:00 local time to the same biological night (flight_night_date) so a moth caught at 23:30 and another at 01:15 are not falsely treated as two consecutive nights for sustained biofix.

UI-01 · Replace OBLR trap-threshold display with 3% foliar scouting prompt and add CM/OFM threshold gating

⚬ Severity: high     Confidence: Sure     Effort: S

⚬ Where: server/sentinel_server/services.py (phenology_status) and server/sentinel_server/templates/

⚬ Evidence: UMass & USU Extension: "Oblique-banded leafrollers: No trap thresholds have been established for OBLR" (https://www.umass.edu/agriculture-food-environment/sites/ag.umass.edu/files/newsletters/healthy_fruit_-_vol._27_no._12_june_25_2019.pdf); Cornell Extension: 3% infested clusters/terminals threshold (https://rvpadmin.cce.cornell.edu/uploads/doc_297.pdf)

⚬ What goes wrong: Applying a moth-per-trap threshold to OBLR misleads growers into either spraying unnecessarily when woodland males enter traps or skipping needed sprays at 350–360 DD43. Conversely, displaying CM/OFM second-generation degree-day windows (1,260 DD50, 1,450 DD45) without checking whether weekly catch exceeds 5 moths/trap/wk (CM) or 10 moths/trap/wk (OFM) recommends sprays when populations are below economic thresholds.

⚬ Fix: Encode the two-variable decision matrix (current_dd, weekly_moths_per_trap) in phenology_status() so every block banner evaluates both heat units and the species-specific threshold rule.

Ranked Feature List for the Orchard Sentinel Dashboard

The table below ranks the recommended dashboard features by Value-to-Effort ratio for a small student capstone team operating over a single field season on a Raspberry Pi 5 server (FastAPI + SQLite + Jinja2) (uploaded:00_ARGON_BRIEF.md).

Rank	Feature ID & Title	Primary User	Effort	Confidence	Value & Rationale (Why It Matters This Season)
1	F-01: Plain-Language "What to Do This Week" Decision Banner per Block	Grower, Consultant	S (1 day)	Sure	Directly answers the grower's #1 question ("Do I need to spray, when, and which block?") by combining NEWA Baskerville-Emin DD, 5-day forecasted DD date, and weekly trap thresholds (5/wk CM, 10/wk OFM, 3% scouting OBLR).
2	F-02: Dual Biofix Tracker (1st Catch vs. Sustained) + 1-Tap Manual Override + Biofix Verification Gate	Grower, Scout	S (1 day)	Sure	Prevents a single unreviewed false positive from ruining the season's DD clock; allows growers to lock or override the biofix date to match their local NEWA profile or extension advisor.
3	F-03: Trap Photo Inspector with Color-Coded Bounding Boxes (Trapview Pattern) & Look-Alike Guide	Grower, Scout	S (1–2 days)	Sure	Builds immediate trust in automatic counts by boxing verified targets (CM, OFM, OBLR) in solid green, unverified AI candidates in dashed amber, and non-targets (RBLR, flies, debris) in muted gray (https://u.osu.edu/vegnetnews/2023/04/29/hal-9000-meets-insect-monitoring-introducing-trapview-camera-traps/).
4	F-04: Fleet & Trap Health Strip (Hub Online, Battery V, Last Photo, Liner Age/Saturation, Lure Age)	Student Team, Scout, Grower	S (1 day)	Sure	Answers "Is anything broken?" on the first screen. Flags silent failures (hub offline >6\text{ hrs}, node missed \ge 2 check-ins, liner >14\text{ days} or >50\% covered, lure >28\text{ days} old, glare >15\%) (https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.pdf).
5	F-05: SMS & Email Alert Engine (Biofix Candidate, Spray Window in 48h, Threshold Exceeded, Hub Offline)	Grower, Student Team	S–M (2 days)	Sure	Farmers do not check a web app daily in mid-summer. Sending high-signal SMS alerts via Twilio/SMTP gateway ensures critical biofix and spray windows are never missed.
6	F-06: Lightweight HTML/SVG Degree-Day & Weekly Catch Trend Chart with Forecasted Milestone Date	Grower, Consultant	M (2–3 days)	Sure	Plots weekly moth catch bars against the threshold line (5/wk or 10/wk), overlays cumulative DD with vertical milestone markers (250 DD50, 360 DD50, 1,260 DD50), and projects the exact calendar date of the next milestone using 5-day NWS/NEWA temperature forecasts.
7	F-07: Rapid Batch Review Queue with Keyboard Shortcuts & Look-Alike Comparison Crops	Scout, Student Team	S (1–2 days)	Sure	Enables a scout or student to confirm/correct 50+ unsure crops in 2 minutes using 1–6 hotkeys, showing previous/next track frames to verify whether an insect shifted or arrived newly.
8	F-08: 1-Tap "Log Spray / Reset Threshold" & NYSDEC / Eco-Apple Audit CSV+Print Export	Grower, Consultant	M (2–3 days)	Sure	Allows logging a spray event (Product, EPA Reg #, IRAC Group, Rate, Acres, REI/PHI) which plots on the trap chart, checks IRAC MoA rotation between generations, and exports a 1-page printable/CSV report meeting 6 NYCRR 325.25 and Eco-Apple IPM justification audits.
9	F-09: Block-Level Aggregation (Farm \rightarrow Block \rightarrow Trap) & Consultant Multi-Farm Triage Table	Consultant, Large Grower	M (3 days)	Sure	Groups multiple traps per block (showing Block Avg and Block High catch) and provides scouts with a single cross-farm triage view and "Liner/Lure Maintenance Route Checklist".
10	F-10: Low-Signal Offline Caching (Service Worker + Persistent 90-Day Login + <40 KB Overview Page)	Grower, Scout	S (1 day)	Likely	Keeps users logged in all season (https://www.winfieldunited.com/news-and-insights/z-trap-system) and caches the latest HTML summary and block table so a grower in an orchard dead zone can still read spray timings.

Page-by-Page Specification for Version 1 (Server-Rendered Jinja2 + 1 CSS File)

To respect the Raspberry Pi 5 server constraint and existing FastAPI + Jinja2 architecture (uploaded:00_ARGON_BRIEF.md), Version 1 requires five core pages (plus a print/CSV stylesheet), designed mobile-first (375px minimum viewport width, high-contrast sunlight theme #FFFFFF background / #111111 text, $\ge 48\text{ px}$ touch targets, zero heavy JS frameworks).

Page Route & Name	Primary Persona & Purpose	Top-to-Bottom Layout & Exact UI Components	Low-Signal, Sunlight & Trust Behaviour
Page 1: Orchard Overview (The First Screen)
GET /	Grower (in truck) & Consultant (morning triage): Immediate answer to "Do I need to spray, which block, and is anything broken?" in <5\text{ seconds}.	1. Top Status Bar: Farm selector dropdown (or "All Client Farm[span_173](start_span)[span_173](end_span)s" for consultants), last weather sync timestamp (NEWA Station: Geneva), and global System Health Pill ("All 12 Traps Online" in Green, or "1 Trap Needs Liner / 1 Hub Offline" in Amber/Red).
2. Pending Verification Banner (Conditional): Appears only if a Biofix Candidate is waiting in the Review Queue ("1 New Moth in Block A may set CM Biofix — [Tap to Verify Photo]").
3. "What to Do This Week" Action Cards (Sorted by Urgency: Red \rightarrow Amber \rightarrow Green): One card per Block \times Pest. Displays: Block Name, Pest Badge (CM, OFM, OBLR), Status Pill (SPRAY WINDOW OPEN, WATCH / PREPARE SPRAY, SCOUT TERMINALS, or NO ACTION NEEDED), the exact plain-language action message (see table below), plus 4 key metrics: Biofix Date (Verified/Override badge), Current DD (and forecasted DD in 5 days), This Week's Catch (Avg / High moths vs. threshold), and Last Spray / Rain Since Spray.
4. Trap & Hub Maintenance Footer Table: Collapsible list of only traps needing physical attention (Battery < 3.5V, Liner > 14d or >50% full, Lure > 35d, Missed >= 2 check-ins).	No full-size images loaded on Page 1. Total payload <35\text{ KB} (renders in <0.5\text{ s} on 1 bar of LTE). Cached by Service Worker for offline reading. High-contrast status borders (4px solid #D93025 for Red, #FA903E for Amber, #1E8E3E for Green) paired with text icons so colorblind users in bright sun can read instantly.
Page 2: Block & Trap Detail Page
GET /blocks/{block_id}	Grower & Scout: Deep dive into degree-day progression, weekly catch trends vs. threshold, biofix settings, and spray logging.	1. Header & Biofix Control Bar: Block name, cultivar, acreage, NEWA station selector, and Biofix Control Box: shows First Confirmed Catch: May 12, Sustained Biofix: May 15 [Active], and a [Change / Override Biofix Date] button (using native YYYY-MM-DD input or quick presets, never a rotary dial).
2. Inline SVG Degree-Day & Catch Trend Chart: Vertically stacked two-panel SVG chart (zero JS library weight):
• Top Sub-Chart (Degree Days): Cumulative DD curve (DD50, DD45, or DD43 BE) with shaded horizontal bands for Ovicidal Window, 1st Gen Larvicidal Window, and 2nd Gen Window, plus a dashed 5-day NWS/NEWA forecast projection line showing the exact date the curve crosses the next milestone.
• Bottom Sub-Chart (Weekly Catch vs. Threshold): Weekly bar chart of new target moths per trap (Block Avg and Block Max), overlaid with a bold red horizontal dashed threshold line (5/wk for CM, 10/wk for OFM; omitted for OBLR with note "No trap threshold — time by DD & 3% larval scouting") and vertical markers showing logged Spray Dates (with IRAC Group badge) and Rainfall >1.5\text{ in.}
3. Per-Trap Cards & Latest Thumbnail Strip: For each trap in the block, shows the latest cropped card preview, new moths today, total moths on current liner, liner age, lure age, battery voltage (V), RSSI (dBm), and two big buttons: [Inspect Latest Photo] and [Mark Liner / Lure Replaced].
4. Action Buttons: [+ Log Spray / Scouting Result] and [Export / Print Block IPM Report].	Uses server-rendered inline <svg> so charts render instantaneously without client-side Chart.js/D3 downloads and print cleanly to PDF. Includes a "High Temp Pyrethroid Warning" badge if forecast highs exceed 85°F during a spray window (https://nyshs.org/wp-content/uploads/2017/12/Jentsch-Pages-27-32-from-NYFQ-Fall-Book-2017-4.pdf).
Page 3: Photo & Track Inspector
GET /captures/{capture_id}	Grower & Scout: Visual proof of what is on the sticky card to build trust in counts (https://www.aces.edu/wp-content/uploads/2021/04/ANR-2724-ModernInsectTraps_040721L-G.pdf).	1. Capture Metadata Bar: Trap name, local timestamp (May 18, 2026, 6:00 AM EDT), scale reading (15.3 px/mm — ArUco/Grid OK or warning if scale fallback used), glare % (8%), and previous/next photo navigation arrows ([< Prev Photo] [Next Photo >]).
2. Interactive Bounding-Box Overlay (Trapview Convention): Displays the undistorted sticky card image with toggleable SVG bounding boxes:
• Solid Green Box: Human-verified target (CM, OFM, OBLR) with track ID and arrival date.
• Dashed Amber Box: AI-predicted target awaiting confirmation (shows top-1 label + confidence, e.g., CM 84%).
• Muted Gray Box: Non-target bycatch (other_moth like RBLR, other_insect, debris)—hidden by default with a [Show 14 Non-Targets] toggle so the grower sees why they were excluded.
3. Track Crop List (Below Photo): Grid of 150 \times 150\text{ px} high-res crops of every insect counted on the current liner, showing measured wingspan/length in \text{mm} (11.2 [span_180](start_span)[span_180](end_span)mm), arrival date, and a 1-tap [Confirm] or [Change ID] dropdown.	Serves progressive WebP/JPEG (~120 KB compressed view by default, with a [Load Full 3MP Original] link for cellular data savings). Pinned at the top of the crop list is a Visual Reference Strip comparing actual CM (10-12 mm, bronze wingtip), OFM (6-8 mm, mottled gray), OBLR (19-25 mm, 3 oblique bands), and RBLR (smaller off-target leafroller).
Page 4: Scout & Student Review Queue
GET /review	Scout, Consultant & Student Team: Rapidly confirm unsure classifications, verify biofix candidates, and audit 1-in-10 spot checks.	1. Priority Filter Tabs: Biofix Candi[span_155](start_span)[span_155](end_span)dates (2) (Red tab, always first) \rightarrow Low-Confidence Targets (9) \rightarrow 1-in-10 Spot Checks (5).
2. Track Comparison Card: For each item, shows:
• High-res crop of the insect on Day t alongside the same card patch on Day t-1 (Before Arrival) and Day t+1 so the reviewer can instantly verify it is a new arrival and not glue glare or a shifted moth.
• Measured size in \text{mm} (from grid/ArUco scale) vs. expected species range (CM: 10–12 mm, OFM: 6–8 mm, OBLR: 19–25 mm).
• Six large (56\text{ px} tall) 1-tap classification buttons with keyboard hotkeys: [1: CM], [2: OFM], [3: OBLR], [4: Other Moth (RBLR/LAW)], [5: Other Insect], [6: Debris/Glare], plus [Confirm All High-Confidence on Page].	Pre-fetches the next 5 small crop thumbnails (<15\text{ KB} each) so clicking a classification button advances to the next track in <50\text{ ms} with zero full-page reload delay.
Page 5: Setup, Alerts & Compliance Export
GET /settings & GET /reports/export	Grower, Consultant & Student Team: Configure SMS/email alerts, manage hubs/traps, and export audit-ready spray/scouting records.	1. Alert Preferences Form: Phone numbers (SMS) and emails per role; checkboxes for: Biofix Candidate, Spray Window Approaching (48h), Weekly Catch Above Threshold, and Hub/Camera Offline >12h.
2. Hub & Camera Provisioning Table: Lists each Hub (Tailscale IP, last heartbeat, disk queue depth, Pi CPU temp) and each ESP32-S3 node (wake schedule, last check-in, battery V, RSSI dBm, [Request Photo Now] button, and [Reset Liner / Lure] button).
3. NYSDEC (6 NYCRR 325.25) & Eco-Apple Audit Export / Print View (GET /reports/export): Date-range selector and [Download CSV] / [Print PDF Summary] buttons. Generates a clean @media print table containing: Farm/Block Address & 5-digit ZIP, Target Pest, Biofix Date, Accumulated DD at Spray, Weekly Trap Count (Avg/High), Verified Photo ID, plus logged Spray Product, EPA Reg. No., Undiluted Quantity, Dosage Rate, Method, Applicator Cert. #, REI, and PHI (https://www.nysprl.com/PRLRecordkeepingRequirementsforApplicators.pdf, https://extapps.dec.ny.gov/docs/materials_minerals_pdf/privatercdfr.pdf, https://ipminstitute.org/wp-content/uploads/2026/04/2026-Red-Tomato-Eco-Stone-Fruit-Supplement-v3.5.pdf).	@media print CSS strips all navigation bars, buttons, and dark backgrounds, formatting a clean black-and-white multi-block table that a grower can hand directly to a NYSDEC inspector, Eco-Apple auditor, or tractor spray operator.

Exact Wording of the Main "What to Do This Week" Messages by Pest

The following table provides the exact literal UI strings to render inside the primary "What to Do This Week" banner on Page 1 (Orchard Overview) and Page 2 (Block Detail) for every phenological and threshold state of Codling Moth (CM), Oriental Fruit Moth (OFM), and Obliquebanded Leafroller (OBLR). Each message is written in plain, direct grower language, states the exact decision (SPRAY NOW, PREPARE TO SPRAY, SCOUT, VERIFY PHOTO, or NO SPRAY NEEDED), and cites the exact numbers driving that recommendation.

Pest	Phenological & Threshold State (Trigger Rule in phenology_status)	UI Status Badge	Exact Wording of the Main "What to Do This Week" Banner Message
Codling Moth (CM)	State 1: Pre-Biofix (Traps hung at Pink/Bloom, 0 verified moths)	MONITORING FOR BIOFIX (Blue)	"No codling moth spray needed this week. Traps are active and checking daily for spring flight (0 CM caught so far; regional 1st catch averages ~250 DD50 from Jan 1)."
Codling Moth (CM)	State 2: Biofix Candidate Pending Human Confirmation	VERIFY BIOFIX PHOTO (Amber)	"Action Needed: Confirm photo of {N} candidate codling moth(s) caught on {date}. If verified, this sets your Block Biofix and projects 1st egg-hatch spray (230–250 DD50) around {projected_date}."
Codling Moth (CM)	State 3: Post-Biofix, Pre-Window (0–149 DD50 from Biofix)	TRACKING HEAT UNITS (Green)	"No codling moth spray needed yet. Biofix set on {biofix_date} ({current_dd} DD50 accumulated; {weekly_avg} moths/trap this week). Ovicidal window (150–175 DD50) opens around {ovicide_date}; 1st larvicidal hatch window (230–250 DD50) opens around {larvicide_date}."
Codling Moth (CM)	State 4: 1st Gen Ovicidal / Early IGR Window (150–200 DD50 from Biofix)	OVICIDE / IGR WINDOW (Amber)	"Optional Ovicidal / IGR Window Now ({current_dd} DD50 since {biofix_date}; {weekly_avg} moths/trap/wk). If using an ovicide or early IGR (e.g., Rimon or Intrepid), apply between 150–175 DD50. Otherwise, wait for the main larvicidal egg-hatch spray at 230–250 DD50 (projected {larvicide_date})."
Codling Moth (CM)	State 5A: 1st Gen Larvicidal Window — High/Standard Pressure (220–340 DD50 AND Weekly Catch > 5 moths/trap or High-Risk Block)	SPRAY NOW — 1ST GEN HATCH (Red)	"SPRAY THIS WEEK FOR CODLING MOTH: Block is at {current_dd} DD50 (target window: 230–250 DD50, ~3% egg hatch) and trap catch is {weekly_avg} moths/trap/wk (High trap: {weekly_max}), exceeding the 5 moths/trap/wk threshold. Apply a larvicidal insecticide within 5–7 days and plan a 2nd cover in 10–14 days."
Codling Moth (CM)	State 5B: 1st Gen Larvicidal Window — Low Pressure (220–340 DD50 AND Weekly Catch <= 5 moths/trap in Low-Risk Block)	LOW PRESSURE — WAIT FOR 360 DD (Amber)	"Hold or Prepare Single Spray: Block is at {current_dd} DD50, but codling moth catch is low ({weekly_avg} moths/trap/wk; threshold is 5/wk). In low-pressure blocks, Cornell guidelines allow waiting for a single spray at 360 DD50 (projected {dd360_date}) instead of a two-spray program."
Codling Moth (CM)	State 6: 1st Gen Low-Pressure Single-Spray Window (341–390 DD50 if no spray logged at 230–250 DD50)	SPRAY NOW — 360 DD WINDOW (Red)	"SPRAY THIS WEEK FOR CODLING MOTH: Block has reached {current_dd} DD50 (360 DD50 single-spray window). Apply 1 larvicidal spray now to cover 1st-generation egg hatch. Follow up in 10–14 days ONLY if trap catch stays above 5 moths/trap/wk (current catch: {weekly_avg}/wk)."
Codling Moth (CM)	State 7: 1st Gen Follow-Up / Extended Flight (360–750 DD50, \ge 10–14\text{ days} since 1st spray OR \ge 1.5\text{ in.} rain)	CHECK 2ND COVER NEED (Red if >5\text{/wk}, Green if \le 5\text{/wk})	If >5 moths/trap/wk: "APPLY 2ND COVER FOR CODLING MOTH: It has been {days_since_spray} days ({rain_in} in. rain) since your 1st spray, and catch is {weekly_avg} moths/trap/wk (above the 5/wk threshold at {current_dd} DD50). Reapply within the same IRAC mode-of-action group; inspect 100 fruit/block for entries starting at 550 DD50."
If <=5 moths/trap/wk: "No follow-up spray needed this week ({current_dd} DD50). Trap catch is {weekly_avg} moths/trap/wk (below the 5/wk threshold). Refresh lures around 1,000 DD50 for 2nd generation flight."
Codling Moth (CM)	State 8: 2nd Generation Larvicidal Window (1,200–1,350[span_209](start_span)[span_209](end_span)[span_211](start_span)[span_211](end_span)[span_213](start_span)[span_213](end_span) DD50 from 1st Gen Biofix)	2ND GEN SPRAY GATE (Red if >5\text{/wk}, Green if \le 5\text{/wk})	If >5 moths/trap/wk: "SPRAY THIS WEEK — 2ND GENERATION CODLING MOTH: Block is at {current_dd} DD50 (target window: 1,250–1,300 DD50) and weekly catch is {weekly_avg} moths/trap (above 5/wk threshold). Apply larvicide now and ROTATE to a new IRAC Mode of Action group (Gen 1 used IRAC {gen1_irac})."
If <=5 moths/trap/wk: "No 2nd-generation codling moth spray needed this week. Block is in the 2nd-gen hatch window ({current_dd} DD50), but trap catch is {weekly_avg} moths/trap/wk (below the 5/wk threshold). Continue weekly monitoring."
Oriental Fruit Moth (OFM)	State 1: Pre-Biofix (Early April to Pink)	MONITORING FOR BIOFIX (Blue)	"No oriental fruit moth spray needed this week. Traps are active and checking daily for sustained spring catch (2+ OFM moths/trap)."
Oriental Fruit Moth (OFM)	State 2: 1st Generation Hatch Window (170–200 DD45 early hatch to 350–375 DD45 peak hatch)	1ST GEN HATCH / PETAL FALL (Amber or Red if >10\text{/wk})	"1st Generation OFM Hatch Window ({current_dd} DD45 since {biofix_date}; {weekly_avg} moths/trap/wk). Early hatch is at 170–200 DD45 and peak hatch (55–60%) is at 350–375 DD45. In apples, petal-fall and 1st-cover sprays normally control 1st-brood OFM; ensure targeted larvicidal coverage if catch exceeds 10 moths/trap/wk or in peaches."
Oriental Fruit Moth (OFM)	State 3: 2nd Generation Hatch Window (1,150–1,200 DD45 early to 1,450–1,500 DD45 peak hatch)	2ND GEN THRESHOLD GATE (Red if >10\text{/wk}, Green if \le 10\text{/wk})	If >10 moths/trap/wk: "SPRAY THIS WEEK — 2ND GENERATION OFM: Block is at {current_dd} DD45 (target window: 1,150–1,200 DD45 early / 1,450–1,500 DD45 peak hatch) and trap catch is {weekly_avg} moths/trap/wk, exceeding the 10 moths/trap/wk threshold. Apply 1 larvicidal spray using a rotated IRAC group."
If <=10 moths/trap/wk: "No 2nd-generation OFM spray needed this week. Block is in the 2nd-gen hatch window ({current_dd} DD45), but trap catch is {weekly_avg} moths/trap/wk (below the 10/wk threshold). Scout terminals for any shoot flagging."
Oriental Fruit Moth (OFM)	State 4: 3rd & 4th Generation Windows (2,100–2,500 DD45 Gen 3; Sept Gen 4)	LATE SEASON THRESHOLD GATE (Red if >10\text{ or }15\text{/wk}, Green otherwise)	If >10/wk (Gen 3) or >15/wk (Gen 4): "SPRAY THIS WEEK — LATE GENERATION OFM: Block is at {current_dd} DD45 and trap catch is {weekly_avg} moths/trap/wk (above the {threshold}/wk threshold). Apply a short-PHI larvicide to prevent late pinpoint fruit entry before harvest."
If below threshold: "No OFM spray needed this week ({current_dd} DD45). Weekly catch is {weekly_avg} moths/trap (below the {threshold}/wk action threshold)."
Obliquebanded Leafroller (OBLR)	State 1: Bloom to Petal Fall (Overwintered Larvae — Pre-Flight)	SCOUT BUD CLUSTERS (Amber)	"Scout for Overwintered OBLR Larvae This Week (Bloom to Petal Fall): Inspect bud clusters and expanding terminals for webbed leaves and green caterpillars. Spray at Petal Fall ONLY if 3% or more of clusters/terminals are infested. Hang OBLR pheromone traps at Petal Fall to catch 1st summer adult flight."
Obliquebanded Leafroller (OBLR)	State 2: Post-Biofix, Pre-Hatch (0–320 DD43 from Summer Biofix)	COUNTING TO 350 DD43 (Green)	"No OBLR spray needed this week. Summer flight biofix set on {biofix_date} ({current_dd} DD43 accumulated; {weekly_avg} moths/trap). Note: OBLR has NO moth-per-trap threshold. First summer larval hatch spray (350–360 DD43) is projected for {hatch_date} (~{days_away} days)."
Obliquebanded Leafroller (OBLR)	State 3: 1st Summer Generation Hatch Window (340–380 DD43 from Biofix)	SPRAY WINDOW — 1ST SUMMER HATCH (Red)	"OBLR 1ST SUMMER HATCH WINDOW NOW ({current_dd} DD43 since {biofix_date}; target: 350–360 DD43): In blocks with a history of OBLR fruit damage, apply a leafroller larvicide (e.g., IRAC Group 5, 18, 28, or Bt) this week to control newly hatching larvae, and follow up in 10–14 days (or after 1.5–2 in. of rain)."
Obliquebanded Leafroller (OBLR)	State 4: Summer Terminal & Cluster Scouting Window (550–700 DD43 from Biofix / Early July)	SCOUT TERMINALS (3% RULE) (Amber)	"Scout Shoot Terminals & Fruit Clusters for OBLR Larvae ({current_dd} DD43 since biofix): Examine expanding shoot terminals and fruit clusters using the Cornell sequential sampling chart. Apply a summer larvicide ONLY if 3% or more of terminals/clusters have live OBLR larvae."
All Pests (CM, OFM, OBLR)	Modifier Warning: Forecast High \ge 85^\circ\text{F} During Active Spray Window	HEAT EFFICACY WARNING (Appended to Red Banner)	"Weather Warning: Forecast highs reach {max_temp_f}°F this week. Avoid pyrethroids (IRAC Group 3, e.g., Warrior/Brigade), which lose up to 9.5x–13.6x efficacy above 85–95°F; use a diamide, spinosyn, or IGR instead."




Sources used in the report
  About Degree Days - NEWA (cornell.edu)

  Integrated Pest Management Crop Production Tools | NEWA

  Codling Moth (Cydia pomonella) | Cornell IPM Fact Sheet

  Codling Moth - Extension Barron County

  Proposal/Project Management System (PPMS)

  The resurgence of Codling Moth in the Hudson Valley

  NEWA 3.0 - what you need to know - UMass Amherst

  Scaffolds Podcast Digest: Season 4, Episode 9 (May 26 2026)

  Agriculture & Horticulture - Cornell Cooperative Extension

  Don't trust the calendar: Why trapping matters during unusual weather

  Weekly Report 5/8/2025 | NY Tree Fruit Pest Monitoring Network

  Updates to NEWA functions | - UVM Blogs - University of Vermont

  When Obliquebanded Leafroller (OBLR) Fly - Cornell blogs

  Obliquebanded Leafroller Management for Apple Production

  Rolling On: Obliquebanded Leafroller Emergence. June 21st.

  Final Report for ONE04-017 - SARE Grant Management System

  Weekly Update 7/1/2025 | NY Tree Fruit Pest Monitoring Network

  Weekly Update 7/21/2025 | NY Tree Fruit Pest Monitoring Network

  The tools I want where I want - NEWA - Cornell University

  Tree Fruit Insect Pest - Codling Moth - Penn State Extension

  Tree Fruit Insect Pest - Obliquebanded Leafroller

  Insect Pest Identification and Control | Penn State Extension

  Tree Fruit Insect and Mite Control Toolbox - Pesticide Resistance

  Insect Pest Identification and Control - Penn State Extension

  Weekly Report 5/13/24 | NY Tree Fruit Pest Monitoring Network

  Building site-specific capacity by integrating weather networks and

  NEWA Workshop Program Key Takeaways

  Fruit IPM Reports - UNH Extension

  Agrobiodiversity For Pest Management: An Integrated Bioeconomic

  2026 Weekly Update #7 – 5/12/2026 – Petal fall and warmer weather

  2026 Weekly Update #17 – 7/28/2026 Anticipating Harvest

  Using Degree-Day Models and Camera Traps to Manage Codling

  Fruit IPM Report for Week of 5/18/2026 - Plant & Pest Advisory

  Healthy Fruit, Vol. 27, No. 12, June 25, 2019

  Healthy Fruit, Vol. 25, No. 11, June 13, 2017 - UMass Amherst

  No Slide Title

  “Fruit Facts” – Frday, October 1, 2021

  2026 Weekly Update #10 – 6/2/2026 – Warming Up | NY Tree Fruit

  Healthy Fruit, Vol. 23, No. 15, August 4, 2015

  Row crops - Trapview

  HAL 9000 Meets Insect Monitoring: Introducing Trapview Camera

  Can AI improve insect monitoring? Lessons from Moth Trapping

  Wisecrop and Trapview: monitor to predict

  Trapview - Automated pest-monitoring system for sustainable

  Technical Assistance to Establish Solar Energy Based E-Pest

  Semios Hub - App Store - Apple

  How Better Data Is Transforming Integrated Pest Management

  Advantages of Smart Pest Traps in Your Nut Orchard

  Top Agricultural Pheromone Companies and IPM Leaders 2026

  PRL: Recordkeeping Requirements for Pesticide Applicators - nysprl

  NY electronic pesticide annual report - TreatLog

  Policy DSHM-PES-05-10 Compliance With The Pesticide Reporting

  N.Y. Comp. Codes R. & Regs. Tit. 6 § 325.25 - Records and reports

  state of new york: department of environmental conservation - NY.gov

  New York pesticide application record - SprayDocs

  New York Commercial Pesticide Applicator Category 7G - Docsity

  PRL: Reporting Requirements for Pesticide Applicators - nysprl

  Checklist for New York State Pesticide Businesses /Agencies/and

  Recordkeeping for WPS and Private Applicators - NY.Gov

  Agworld Pricing 2026 - Capterra

  2026 Petal Fall Insect Management - Cornell blogs

  HEALTHY FRUIT Vol. 21, No. 2, April 9, 2013

  2026 Weekly Update #2 – 4/6/26 – Cold with change coming

  FarmSense automates real-time insect monitoring - Future Farming

  About FarmSense | Real-Time Insect Monitoring Experts

  FarmSense trap tech counts and identifies crop-killing insects

  FarmSense Revolutionizes Pest Control With Next-Generation

  Stuck in the Past | Why Farmers Are Replacing Sticky Traps with

  Z-Trap System - WinField® United

  Modern Insect Pest Monitoring Using Automatic Traps

  Modern Insect Pest Monitoring Using Automatic Traps

  Apple maggot fly traps | - UVM Blogs - University of Vermont

  Obliquebanded Leafroller

  Eco Stone Fruit Supplement | IPM Institute

  Integrated Pest Management - Backyard Fruit Growers

  Book The - Trécé

  Intermountain Tree Fruit Production Guide - USU Extension

  Potential New Management Techniques for Obliquebanded Leafroller

  June 12th, 2025 Weather Outlook - Crops and Soils

  Healthy Fruit, Vol. 26, No. 15, July 17, 2018 - UMass Amherst

  CropTracker Reviews 2026. Verified Reviews, Pros & Cons | Capterra

  Croptracker Reviews 2026: Details, Pricing, & Features - G2

  CropTracker Software Pricing, Alternatives & More 2026 | Capterra

  Croptracker vs. Granular Comparison 2026 | G2

  Conservis vs. Croptracker Comparison 2026 - G2

  Agworld Software Pricing, Alternatives & More 2026 - Capterra

  MyCrops Software Pricing, Alternatives & More 2026 - Capterra

  Agworld Reviews 2026: Details, Pricing, & Features - G2




Sources read but not used
  Codling moth management - UW Fruit Program

  Scaffolds Podcast Digest: Season 4, Episode 17 ... - Cornell blogs

  Grand Rapids area tree fruit update – June 23, 2020

  2021 Hudson Valley Research Lab Scouting Report | CDN

  May 30, AppleTalk Conference Call - IPM Institute

  Healthy Fruit, Vol. 25, No. 8, May 23, 2017 - UMass Amherst

  Weekly Report 6/10/2025 | NY Tree Fruit Pest Monitoring Network

  Weekly Report 5/27/2025 | NY Tree Fruit Pest Monitoring Network

  Weekly Report 6/17/2025 | NY Tree Fruit Pest Monitoring Network

  Weekly Report 6/24/2025 | NY Tree Fruit Pest Monitoring Network

  NEWA: Home

  Home | NEWA

  Create Dashboard - NEWA (cornell.edu)

  Tree Fruit Insect Pest - Oriental Fruit Moth - Penn State Extension

  Tree Fruit Insect Pest -Tufted Apple Bud Moth - Penn State Extension

  Tree Fruit Insect Pest - Green Fruitworm - Penn State Extension

  Page 4 | Fruit Pests and Diseases - Penn State Extension

  Orchard IPM (Integrated Pest Management) - An Overview

  Apple Insect and Mite Control Toolbox - Insecticide and Miticide

  Apple Insect and Mite Control Toolbox - Insecticide and Miticide

  CIPRA Computer Centre for Agricultural Pest Forecasting

  Healthy Fruit, Vol. 24, No. 5, April 26, 2016

  Stone Fruit IPM for Beginners

  Tree Fruit News - Regional Vegetable Program Admin

  Building site-specific capacity by integrating weather networks and

  Resource Guide for Organic Insect and Disease Management

  August 20th, 2026 Weather Outlook - Crops and Soils

  Tree Fruit IPM Report May 5, 2025 - Plant & Pest Advisory

  Fruit IPM Report May 20, 2025 - Plant & Pest Advisory

  Fruit IPM Report 5/11/2026 - Plant & Pest Advisory

  October 2nd, 2026 Weather Outlook - Crops and Soils

  PROCEEDINGS

  2018 Hudson Valley Research Lab Scouting Report 7.02.18 - CDN

  Fruit Insect Scouting | Weekly Crop Update

  Crop updates - Specialty crop pest management

  Peach IPM August 3 - Cornell blogs

  NEWA (Network for Environment and Weather Applications

  Grand Rapids area tree fruit update – Aug. 25, 2020

  IPM Scouting Guide - University of Vermont

  New Hampshire IPM Newsletter - UNH Extension

  Row crops - Trapview

  RT#182: Trapview — Pest. Data. Decision. - YouTube

  Automatic Pest Monitoring Systems in Apple Production under

  How Sandhu Bros Farms Holds Navel Orangeworm Damage to 1–4%

  Washington farmer uses Semios to control codling moth in organic

  Regulatory Context for New York Pest Control Services

  Part 325 Rules and Regulations - New York State Arborists

  Forms Related To Pesticides - NYSDEC

  Fall 2020 Stakeholder Meeting Slideshow - NY.Gov

  Part 325 Glyphosate Rulemaking Documents - NY.Gov

  RICHARD GRAHAM, d/b/a R. Graham Pest Control - NY.Gov

  Pesticide Statutes, Regulations, And Policies - NYSDEC

  John Welch Enterprise, Inc. - NY.gov

  OGC 4: Pesticide Recordkeeping And Reporting For Commercial

  Pesticides 1/18/19 Stakeholder Meeting Fact Sheets - NY.Gov

  Obliquebanded Leafroller (4 minutes) – Cornell IPM Help Center

  A Grower's Guide to Organic Apples

  Petal Fall Insect Management Review - Cornell blogs

  Biology and Management of Apple Arthropods

  2026 Weekly Update #15 – 7/7/2026 – Summer lull | NY Tree Fruit

  2026 Weekly Update #14 – 6/30/2026 – Heatwave & Summer Pests

  4/28/2026 – Slow and steady | NY Tree Fruit Pest Monitoring Network

  Pest Monitoring to Protect Your Apples From Codling ... - FarmSense

  FlightSensor by Farmsense | Sensors | AgTech World

  How Automated Pest Monitoring is Transforming Farming - FarmSense

  FarmSense to Demo the Latest Version of Its Real-Time Agricultural

  What Happens When AI Comes to the Cotton Fields | Sustainability

  Spensa Technologies - Grokipedia

  Area-Wide Integrated Pest Management; Development and ... - AWS

  Breaking Barriers to Area-Wide Integrated Management of Insect Pests

  Obliquebanded Leafroller (Choristoneura rosaceana) - Cornell CALS

  2026-2027 intermountain tree fruit production guide

  Parasitoid guild and parasitism rate of the obliquebanded leafroller

  IPM Alert Stage of Development Disease Management

  Healthy Fruit, Vol. 26, No. 13, June 26, 2018 - UMass Amherst

  2024 Integrated Orchard Management Guide for Commercial Apples

  2025 Southeast Apple Management Guide | PDF | Pesticide - Scribd

  Croptracker vs. Kheti Buddy Comparison 2026 | G2

  Best Farm Management Software 2026 - Capterra

  Best Farm Management Software - Page 5 - G2

  Croptracker Products | Read 11 Reviews on G2

  Best CropTracker Alternatives 2026 | Capterra

  fieldmargin Reviews 2026. Verified Reviews, Pros & Cons | Capterra

  Bushel Farm Software Pricing, Alternatives & More 2026 | Capterra




Thoughts
