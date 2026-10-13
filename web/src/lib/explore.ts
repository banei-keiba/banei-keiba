/** 探索 UI のデータ（src/banei/export/explore.py が書き出す JSON）と URL の決まり。 */

export interface Metrics {
  n: number;
  win_rate: number;
  top2_rate: number;
  place_rate: number;
  win_roi: number;
  place_roi: number;
}
export type Row = Metrics & Record<string, string | number>;
export type PeriodKey = 'all' | 'recent3';
export interface Period {
  first_season: number;
  last_season: number;
  total: Metrics | null;
  cells: Row[];
  margins?: Record<string, Row[]>;
}
export interface Table {
  axes: string[];
  through_season: number;
  bins: Record<string, string[]>;
  periods: Record<PeriodKey, Period>;
}

/** URL 上の軸の順（explore.py の AXES と同じ）。同じ組み合わせを 2 つの URL にしない。 */
export const AXES: { key: string; name: string }[] = [
  { key: 'popularity', name: '人気' },
  { key: 'post', name: '馬番' },
  { key: 'weight_diff', name: '重量差' },
  { key: 'age', name: '馬齢' },
  { key: 'sex', name: '性別' },
  { key: 'moisture', name: '馬場水分' },
  { key: 'weather', name: '天候' },
  { key: 'month', name: '月' },
];
export const axisName = (key: string) => AXES.find((a) => a.key === key)?.name ?? key;

export const PERIODS: { key: PeriodKey; name: string }[] = [
  { key: 'all', name: '全期間' },
  { key: 'recent3', name: '直近 3 シーズン' },
];
export const periodName = (key: PeriodKey) => PERIODS.find((p) => p.key === key)?.name ?? key;

export const METRICS: { key: keyof Metrics; name: string }[] = [
  { key: 'win_rate', name: '勝率' },
  { key: 'top2_rate', name: '連対率' },
  { key: 'place_rate', name: '複勝率' },
  { key: 'win_roi', name: '単勝回収率' },
  { key: 'place_roi', name: '複勝回収率' },
];

/** 濃淡を付ける最小の出走数。これ未満のマスは振れが大きいので、薄い文字にして色を付けない。 */
export const RELIABLE_N = 100;

const order = (key: string) => AXES.findIndex((a) => a.key === key);

export function pairUrl(x: string, y: string, period: PeriodKey): string {
  const [a, b] = [x, y].sort((p, q) => order(p) - order(q));
  return `/explore/${a}/${b}/${period}/`;
}

export function singleUrl(x: string, period: PeriodKey): string {
  return `/explore/${x}/${period}/`;
}

const modules = import.meta.glob<{ default: Table }>('../data/explore/*.json', { eager: true });

/** 書き出された全表。キーは軸のキーを __ でつないだもの（popularity__moisture）。 */
export const TABLES: Record<string, Table> = Object.fromEntries(
  Object.entries(modules).map(([path, mod]) => [
    path.slice(path.lastIndexOf('/') + 1, -'.json'.length),
    mod.default,
  ]),
);

export const pct = (v: number) => `${v.toFixed(1)}%`;
export const count = (v: number) => v.toLocaleString('ja-JP');
export const seasonRange = (p: Period) => `${p.first_season}〜${p.last_season} シーズン`;
