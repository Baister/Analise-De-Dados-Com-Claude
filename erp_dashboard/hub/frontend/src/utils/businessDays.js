function pad2(n) {
  return String(n).padStart(2, '0');
}

function toStr(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

export function getEaster(year) {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day   = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(year, month - 1, day);
}

export function getHolidaysSP(year) {
  const easter = getEaster(year);
  const fixed = [
    `${year}-01-01`,
    `${year}-01-25`,
    `${year}-04-21`,
    `${year}-05-01`,
    `${year}-07-09`,
    `${year}-09-07`,
    `${year}-10-12`,
    `${year}-11-02`,
    `${year}-11-15`,
    `${year}-11-20`,
    `${year}-12-25`,
  ];
  const moveable = [
    toStr(addDays(easter, -48)),
    toStr(addDays(easter, -47)),
    toStr(addDays(easter, -2)),
    toStr(addDays(easter, 60)),
  ];
  return new Set([...fixed, ...moveable]);
}

export function countBusinessDaysSP(year, month) {
  const holidays = getHolidaysSP(year);
  const daysInMonth = new Date(year, month, 0).getDate();
  let count = 0;
  for (let d = 1; d <= daysInMonth; d++) {
    const dow = new Date(year, month - 1, d).getDay();
    if (dow >= 1 && dow <= 5) {
      const dateStr = `${year}-${pad2(month)}-${pad2(d)}`;
      if (!holidays.has(dateStr)) count++;
    }
  }
  return Math.max(1, count);
}

export function remainingBusinessDaysSP(year, month) {
  const holidays = getHolidaysSP(year);
  const todayStr = toStr(new Date());
  const daysInMonth = new Date(year, month, 0).getDate();
  let count = 0;
  for (let d = 1; d <= daysInMonth; d++) {
    const dow = new Date(year, month - 1, d).getDay();
    if (dow >= 1 && dow <= 5) {
      const dateStr = `${year}-${pad2(month)}-${pad2(d)}`;
      if (!holidays.has(dateStr) && dateStr >= todayStr) count++;
    }
  }
  return Math.max(1, count);
}
