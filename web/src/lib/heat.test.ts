import assert from 'node:assert/strict';
import { test } from 'node:test';
import { heatScale } from './heat.ts';

test('最小は 0、最大は steps', () => {
  const s = heatScale([10, 20, 30]);
  assert.equal(s(10), 0);
  assert.equal(s(30), 4);
});

test('最小〜最大を 5 等分する', () => {
  const s = heatScale([0, 100]);
  assert.deepEqual([0, 19.9, 20, 59.9, 60, 80, 100].map(s), [0, 0, 1, 2, 3, 4, 4]);
});

test('全部同じ値なら 0（0 除算しない）', () => {
  assert.equal(heatScale([5, 5, 5])(5), 0);
});

test('対象のマスが無ければ 0', () => {
  assert.equal(heatScale([])(42), 0);
});

test('範囲外の値も 0〜steps に収まる', () => {
  const s = heatScale([10, 20]);
  assert.equal(s(-100), 0);
  assert.equal(s(1000), 4);
});
