import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, dirname, resolve} from 'node:path';
import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);
const {build} = createRequire(require.resolve('vite/package.json'))('esbuild');
const temp = await mkdtemp(join(tmpdir(), 'insightbridge-charts-'));
await build({entryPoints: ['src/BIChart.tsx'], outfile: join(temp, 'charts.cjs'), bundle: true, platform: 'node', format: 'cjs', logLevel: 'silent'});
const {buildOption, chartOptions} = createRequire(import.meta.url)(join(temp, 'charts.cjs'));
if (resolve(dirname(temp)) !== resolve(tmpdir())) throw new Error('Unexpected test output directory');
await rm(temp, {recursive: true});

test('shares reject negatives and all-zero values rather than hiding losses', () => {
  for (const kind of ['pie', 'donut', 'treemap']) {
    assert.equal(buildOption({columns:['name','value'],rows:[['a',-1],['b',2]]},kind,'name',['value'],'en-US'),null);
    assert.equal(buildOption({columns:['name','value'],rows:[['a',0]]},kind,'name',['value'],'en-US'),null);
  }
});
test('histogram counts include maximum, repeated values, zeros and exclude nulls', () => {
  const data = {columns:['value'],rows:[[0],[0],[1],[4],[null]]};
  const option = buildOption(data,'histogram','value',['value'],'en-US');
  assert.equal(option.series[0].data.reduce((a,b)=>a+b,0),4);
  assert.deepEqual(buildOption({columns:['v'],rows:[[7],[7]]},'histogram','v',['v'],'en-US').series[0].data,[2]);
});
test('scatter preserves numeric axes and rejects the same measure on both axes', () => {
  const data = {columns:['x','y'],rows:[[1,2],[3,null],[4,5]]};
  assert.equal(buildOption(data,'scatter','x',['x'],'en-US'),null);
  assert.deepEqual(buildOption(data,'scatter','x',['y'],'en-US').series[0].data,[[1,2],[4,5]]);
});
test('multi-series trend pivots categories with gaps, not fabricated zeros', () => {
  const data = {columns:['month','category','gmv'],rows:[['Jan','a',10],['Jan','b',20],['Feb','a',30]]};
  assert.ok(chartOptions(data).types.includes('heatmap'));
  const option = buildOption(data,'line','month',['gmv'],'en-US');
  assert.deepEqual(option.xAxis.data,['Jan','Feb']);
  assert.deepEqual(option.series.map(s=>s.data),[[10,30],[20,null]]);
});
test('heatmap uses categorical coordinates and preserves negative values', () => {
  const data = {columns:['x','y','v'],rows:[['a','b',-3],['c','b',5]]};
  const option = buildOption(data,'heatmap','x',['v'],'en-US');
  assert.deepEqual(option.series[0].data,[[0,0,-3],[1,0,5]]);
  assert.equal(option.visualMap.min,-3);
});
test('ambiguous duplicate categories do not offer misleading share charts', () => {
  const options = chartOptions({columns:['category','value'],rows:[['a',1],['a',2]]});
  assert.ok(!options.types.includes('pie'));
  assert.ok(options.types.includes('histogram'));
});
