/** 騎手・調教師ページのデータ（src/banei/export/people.py が書き出す people.json）と URL の決まり。 */
import data from '../data/people.json';
import { count, pct } from './explore';

export interface Metrics {
  n: number;
  win_rate: number;
  top2_rate: number;
  place_rate: number;
  win_roi: number;
  place_roi: number;
  wins: number;
  avg_popularity: number;
  expected_wins: number;
  wins_over_expected: number;
}
export interface SeasonRow extends Metrics {
  season: number;
}
export interface Career extends Metrics {
  first_season: number;
  last_season: number;
}
export interface Person {
  key: string;
  seasons: SeasonRow[];
  pooled_seasons: number[];
  career: Career | null;
}
export interface SeasonTotal {
  season: number;
  total: Metrics;
  other: (Metrics & { people_count: number }) | null;
}
export type Role = 'jockey' | 'trainer';
export interface Page {
  slug: string;
  name: string;
  name_confirmed: boolean;
  jockey: string | null;
  trainer: string | null;
  active: boolean;
}
export interface PeopleData {
  through_season: number;
  roles: Record<Role, { seasons: SeasonTotal[]; people: Person[] }>;
  pages: Page[];
}

export const PEOPLE = data as unknown as PeopleData;

export const ROLES: { key: Role; name: string; runs: string; verb: string }[] = [
  { key: 'jockey', name: '騎手', runs: '騎乗数', verb: '騎乗' },
  { key: 'trainer', name: '調教師', runs: '出走数', verb: '出走' },
];
export const roleOf = (role: Role) => ROLES.find((r) => r.key === role)!;

/** そのページに載せる役割（騎手を先に）。 */
export const rolesOf = (page: Page): Role[] =>
  ROLES.map((r) => r.key).filter((r) => page[r] !== null);
export const rolesLabel = (page: Page) => rolesOf(page).map((r) => roleOf(r).name).join('・');

export const personOf = (role: Role, key: string): Person =>
  PEOPLE.roles[role].people.find((p) => p.key === key)!;
export const pageOf = (role: Role, key: string): Page =>
  PEOPLE.pages.find((p) => p[role] === key)!;
export const pageUrl = (page: Page) => `/people/${page.slug}/`;

/** シーズンの期間（2025 → 2025/4/1〜2026/3/31）。 */
export const seasonSpan = (season: number) => `${season}/4/1〜${season + 1}/3/31`;

/** 見込みとの差。正の値に + を付け、負の値はマイナス記号（−）にする。 */
export const signed = (v: number) =>
  v > 0 ? `+${v.toFixed(1)}` : v < 0 ? `−${Math.abs(v).toFixed(1)}` : '0.0';

/** シーズン別の表に並べる指標（出走数の後）。率の書式は探索 UI と同じ。 */
export const COLUMNS: { key: keyof Metrics; name: string; fmt: (v: number) => string }[] = [
  { key: 'win_rate', name: '勝率', fmt: pct },
  { key: 'top2_rate', name: '連対率', fmt: pct },
  { key: 'place_rate', name: '複勝率', fmt: pct },
  { key: 'win_roi', name: '単勝回収率', fmt: pct },
  { key: 'place_roi', name: '複勝回収率', fmt: pct },
  { key: 'avg_popularity', name: '平均人気', fmt: (v) => v.toFixed(2) },
  { key: 'wins', name: '勝ち数', fmt: count },
  { key: 'expected_wins', name: '見込み勝ち数', fmt: (v) => v.toFixed(1) },
  { key: 'wins_over_expected', name: '見込みとの差', fmt: signed },
];
