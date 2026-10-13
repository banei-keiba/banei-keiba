/**
 * マスの値を濃淡の段階に変える関数を返す。
 *
 * 表の中の最小〜最大を steps + 1 等分し、0（濃淡なし）〜 steps の段階にする。
 * 対象のマスが無いとき・全部同じ値のときは常に 0（0 除算しない）。
 * 渡すのは出走数 100 以上のマスの値だけ（少ないマスは振れが大きいので色で目を引かせない）。
 */
export function heatScale(values: number[], steps = 4): (v: number) => number {
  if (values.length === 0) return () => 0;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  if (hi === lo) return () => 0;
  return (v) => Math.min(steps, Math.max(0, Math.floor(((v - lo) / (hi - lo)) * (steps + 1))));
}
