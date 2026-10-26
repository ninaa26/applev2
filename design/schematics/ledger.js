// Ledger variants: the grower's plan, worked out once from data.js so all three versions agree.
// Dates come from degree days to go ÷ this week's rate, the same arithmetic phenology.py uses.
(() => {
  const { TODAY, traps, pheno, daily, sum, LINER_MAX_DAYS } = window.OS;
  const add = (n) => new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate() + n);
  const daysTo = (sp, dd) => Math.ceil((dd - pheno[sp].dd) / pheno[sp].rate);
  const fmt = (d, o = { weekday: 'short', month: 'short', day: 'numeric' }) => d.toLocaleDateString('en-US', o);
  const range = (a, b) => `${fmt(a, { month: 'short', day: 'numeric' })}–${b.getMonth() === a.getMonth() ? b.getDate() : fmt(b, { month: 'short', day: 'numeric' })}`;

  const blocks = [
    { id: 'A', name: 'Block A', variety: 'Gala', acres: 6.5, traps: ['T1', 'T2'] },
    { id: 'B', name: 'Block B', variety: 'Honeycrisp', acres: 4.0, traps: ['T3', 'T4'], oblrHistory: true },
    { id: 'C', name: 'Block C', variety: 'Empire', acres: 5.5, traps: ['T5', 'T6'] },
  ];

  const cm1 = add(daysTo('CM', 250));            // first CM spray at 250 DD
  const cm2a = add(daysTo('CM', 250) + 10), cm2b = add(daysTo('CM', 250) + 14);
  const oblr1 = add(daysTo('OBLR', 350));        // OBLR larval spray at 350 DD, blocks with a history
  const oblr2a = add(daysTo('OBLR', 350) + 10), oblr2b = add(daysTo('OBLR', 350) + 14);
  const ofmFlight = add(daysTo('OFM', 965));     // OFM next generation starts flying

  // Spray and scouting jobs, soonest first. kind: spray | watch
  const jobs = [
    { kind: 'spray', sp: 'CM', date: cm1, title: 'Codling moth, first spray', where: 'All blocks', why: `Eggs from this flight start hatching. ${pheno.CM.dd} of 250 degree days since the May 18 biofix, gaining ${pheno.CM.rate} a day.` },
    { kind: 'spray', sp: 'OBLR', date: oblr1, title: 'Leafroller larval spray', where: 'Block B only', why: 'Only blocks with leafroller damage last year. Block B is the one.' },
    { kind: 'spray', sp: 'CM', date: cm2a, end: cm2b, title: 'Codling moth, second spray', where: 'All blocks', why: '10 to 14 days after the first.' },
    { kind: 'watch', sp: 'OFM', date: ofmFlight, title: 'Oriental fruit moth flight 2 starts', where: 'Blocks A and C', why: 'No spray yet. The trap count tells you when its eggs hatch.' },
    { kind: 'spray', sp: 'OBLR', date: oblr2a, end: oblr2b, title: 'Leafroller, second spray', where: 'Block B only', why: '10 to 14 days after the first.' },
  ].sort((a, b) => a.date - b.date);

  // Liners are changed every LINER_MAX_DAYS days: due date per trap (overdue ones are due today).
  const liners = traps.map((t) => ({ trap: t, due: add(Math.max(0, LINER_MAX_DAYS - t.linerDays)), overdue: t.linerDays > LINER_MAX_DAYS }));

  // Round jobs: things a person has to go and do.
  const t5 = traps.find((t) => t.id === 'T5'), t3 = traps.find((t) => t.id === 'T3');
  const rounds = [
    { id: 'r1', level: 'fix', title: 'Swap the battery in Road Block T5', detail: `No photo since Sunday 13:02. Last battery reading ${t5.battery.toFixed(2)} V.`, block: 'C' },
    { id: 'r2', level: 'do', title: 'Change the liner in Honeycrisp Hill T3', detail: `In for ${t3.linerDays} days. Old glue catches less.`, block: 'B' },
    { id: 'r3', level: 'do', title: 'Confirm 6 insects from this morning', detail: 'About 2 minutes. They count once you say yes.', block: null },
  ];

  // Catch this week against the week before, orchard-wide.
  const wk = (sp, from, to) => sum(daily[sp].slice(from, to));
  const catchRows = ['CM', 'OFM', 'OBLR'].map((sp) => ({ sp, now: wk(sp, -7), before: wk(sp, -14, -7) }));

  console.assert(cm1 < oblr1 && oblr1 < cm2a, 'job order');
  window.LG = { blocks, jobs, liners, rounds, catchRows, fmt, range, add, cm1 };
})();
