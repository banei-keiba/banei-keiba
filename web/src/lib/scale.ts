/** 軸目盛りを丸い数値に揃える。0 / 50 / 100 のように読める値だけを置く。 */
export function niceTicks(min: number, max: number, count = 4): number[] {
  const lo = Math.min(min, max);
  const hi = Math.max(min, max);
  const span = hi - lo || Math.abs(hi) || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  // 1 / 2 / 2.5 / 5 / 10 の刻み。2.5 を入れると 0-100 の軸が 0/25/50/75/100 になる
  const step = (norm >= 5 ? 10 : norm >= 2.5 ? 5 : norm >= 2 ? 2.5 : norm >= 1 ? 2 : 1) * mag;
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= end + step * 1e-6; v += step) {
    ticks.push(Number(v.toPrecision(12)));
  }
  return ticks;
}

/** 角丸の上端を持つ縦棒。データ端は 4px 丸め、ベースライン側は角のまま。 */
export function columnPath(x: number, y: number, w: number, h: number, r = 4): string {
  const rr = Math.max(0, Math.min(r, w / 2, h));
  return [
    `M${x},${y + h}`,
    `L${x},${y + rr}`,
    `Q${x},${y} ${x + rr},${y}`,
    `L${x + w - rr},${y}`,
    `Q${x + w},${y} ${x + w},${y + rr}`,
    `L${x + w},${y + h}`,
    'Z',
  ].join(' ');
}
