// Orchard Sentinel schematics: one sample in-season day, shared by all ten directions.
// Shapes follow server/sentinel_server (overview rows, health, pheno.outlook, review queue). Every total
// on a screen is computed from these rows; the asserts at the bottom fail loudly in the console if not.
// Sample data: replace with the server's real rows when a direction is built into the templates.
(() => {
  const TODAY = new Date(2027, 5, 15); // Tue Jun 15 2027, mid-season, so every pest model has something to say
  const DAYS = 30;
  const day = (i) => new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate() - (DAYS - 1 - i));

  // Orchard-wide new catches per day, oldest first (May 17 … Jun 15). The last 7 are "this week".
  const daily = {
    CM:   [0,2,3,2,1,0,1,2,1,0,0,1,0,1,0,1,2,1,1,0,1,2,1, 1,2,3,1,2,3,1],
    OFM:  [4,5,3,6,4,3,2,3,2,2,1,1,2,0,1,1,0,1,2,1,2,1,3, 2,3,1,4,2,3,2],
    OBLR: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1, 0,1,1,0,2,1,1],
    other_moth: [1,0,0,1,0,0,0,1,0,0,1,0,0,0,1,0,0,0,0,1,0,0,0, 1,0,0,1,0,0,1],
  };

  const PESTS = ['CM', 'OFM', 'OBLR'];
  const LABEL = { CM: 'Codling moth', OFM: 'Oriental fruit moth', OBLR: 'Obliquebanded leafroller', other_moth: 'Other moths', unclassified: 'Not yet sorted' };

  const hub = { id: 'H1', name: 'Fieldhouse hub', block: 'Barn', state: 'online', seenMin: 1, cameras: 6, link: 'Cellular, 3 bars' };

  // One row per trap: this week's catches by species, health, liner age, battery, review queue.
  const traps = [
    { id: 'T1', name: 'North Gala', block: 'Block A', lure: 'CM',   week: { CM: 9, other_moth: 2 }, pending: 2, state: 'online',  lastMin: 34,  linerDays: 12, battery: 3.94, x: 0.18, y: 0.22 },
    { id: 'T2', name: 'North Gala', block: 'Block A', lure: 'OFM',  week: { OFM: 14, other_moth: 1 }, pending: 3, state: 'online',  lastMin: 34,  linerDays: 12, battery: 3.88, x: 0.36, y: 0.30 },
    { id: 'T3', name: 'Honeycrisp Hill', block: 'Block B', lure: 'CM',   week: { CM: 4 }, pending: 0, state: 'online',  lastMin: 51,  linerDays: 26, battery: 3.71, x: 0.62, y: 0.20 },
    { id: 'T4', name: 'Honeycrisp Hill', block: 'Block B', lure: 'OBLR', week: { OBLR: 6 }, pending: 1, state: 'online',  lastMin: 51,  linerDays: 9,  battery: 3.90, x: 0.80, y: 0.36 },
    { id: 'T5', name: 'Road Block', block: 'Block C', lure: 'CM',   week: {}, pending: 0, state: 'offline', lastMin: 60 * 41, linerDays: 15, battery: 3.31, x: 0.28, y: 0.74 },
    { id: 'T6', name: 'Road Block', block: 'Block C', lure: 'OFM',  week: { OFM: 3 }, pending: 0, state: 'online',  lastMin: 22,  linerDays: 15, battery: 3.86, x: 0.56, y: 0.70 },
  ];
  const LINER_MAX_DAYS = 21;

  // Degree days since each lure's biofix and what the NEWA milestones say next (phenology.py's wording).
  const pheno = {
    CM:   { biofix: new Date(2027, 4, 18), dd: 236, rate: 17, base: 50, top: 250,
            milestones: [{ dd: 50, short: 'Egg laying begins' }, { dd: 100, short: 'Early egg laying' }, { dd: 220, short: 'First eggs hatch' }, { dd: 250, short: 'First spray' }],
            state: 'soon', headline: 'First spray in about 1 day', detail: '14 DD to go, at about 17 DD a day this week. Second spray 10–14 days after.' },
    OFM:  { biofix: new Date(2027, 3, 30), dd: 611, rate: 21, base: 45, top: 965,
            milestones: [{ dd: 50, short: 'Egg laying begins' }, { dd: 200, short: 'Larval spray' }, { dd: 965, short: 'Next flight' }],
            state: 'later', headline: 'Next flight in about 17 days', detail: '354 DD to go, at about 21 DD a day this week.' },
    OBLR: { biofix: new Date(2027, 5, 8), dd: 141, rate: 22, base: 43, top: 600,
            milestones: [{ dd: 350, short: 'Larval spray' }, { dd: 600, short: 'Scout terminals' }],
            state: 'later', headline: 'Larval spray in about 10 days', detail: '209 DD to go, at about 22 DD a day this week. Applies to blocks with a history of OBLR.' },
  };

  // Insects waiting for a person: the model's guess, how sure it was, which trap and when.
  const review = [
    { id: 4412, trap: 'T2', guess: 'OFM', conf: 0.71, at: '06:10', seed: 3 },
    { id: 4409, trap: 'T2', guess: 'OFM', conf: 0.64, at: '06:10', seed: 7 },
    { id: 4401, trap: 'T1', guess: 'CM',  conf: 0.58, at: '06:12', seed: 1 },
    { id: 4398, trap: 'T2', guess: 'other_moth', conf: 0.52, at: 'Mon 18:10', seed: 9 },
    { id: 4390, trap: 'T4', guess: 'OBLR', conf: 0.77, at: 'Mon 18:12', seed: 4 },
    { id: 4377, trap: 'T1', guess: 'CM',  conf: 0.61, at: 'Mon 12:12', seed: 6 },
  ];

  const events = [
    { at: 'Jun 15, 06:12', trap: 'T1', what: 'New photo', note: '2 new insects' },
    { at: 'Jun 15, 06:10', trap: 'T2', what: 'New photo', note: '3 new insects' },
    { at: 'Jun 14, 13:00', trap: 'T5', what: 'Camera went quiet', note: 'Last photo 13:02' },
    { at: 'Jun 11, 09:40', trap: 'T4', what: 'New liner', note: 'Recorded by Sam' },
    { at: 'Jun 8, 18:12',  trap: 'T4', what: 'Biofix set', note: 'OBLR, 2nd week of catches' },
  ];

  // Derived figures, computed once so every screen agrees.
  const sum = (a) => a.reduce((s, v) => s + v, 0);
  const lastWeek = (sp) => sum(daily[sp].slice(-7));
  const week = Object.fromEntries([...PESTS, 'other_moth'].map((sp) => [sp, lastWeek(sp)]));
  const pending = sum(traps.map((t) => t.pending));
  const reporting = traps.filter((t) => t.state === 'online').length;
  const fromTraps = (sp) => sum(traps.map((t) => t.week[sp] || 0));

  for (const sp of [...PESTS, 'other_moth']) console.assert(fromTraps(sp) === week[sp], `week ${sp}: traps ${fromTraps(sp)} vs daily ${week[sp]}`);
  console.assert(pending === review.length, 'pending count must equal the review queue');
  for (const sp of PESTS) { const p = pheno[sp]; console.assert(p.dd <= p.top, `${sp} dd past top`); }

  const dayLabel = (d, o = { month: 'short', day: 'numeric' }) => d.toLocaleDateString('en-US', o);
  const ago = (min) => min < 60 ? `${min} min ago` : min < 60 * 24 ? `${Math.round(min / 60)} h ago` : `${Math.round(min / 60 / 24)} days ago`;
  const peak = Math.max(...daily.CM.map((_, i) => PESTS.concat('other_moth').reduce((s, sp) => s + daily[sp][i], 0)));

  window.OS = { TODAY, DAYS, day, daily, PESTS, LABEL, hub, traps, LINER_MAX_DAYS, pheno, review, events, week, pending, reporting, peak, sum, dayLabel, ago,
    orchard: 'Lansing Ridge Orchard', farmer: 'Lansing Ridge', weekday: dayLabel(TODAY, { weekday: 'long', month: 'long', day: 'numeric' }) };
})();
