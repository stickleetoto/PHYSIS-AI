import {expect,it} from 'vitest'
import {parseData,statistics} from './mathStatistics'
it('matches hand-computed statistics and zero residual for y=2x+1',()=>{
  const r=statistics(parseData('x,y\n0,1\n1,3\n2,5'))
  expect(r.mean).toBe(3);expect(r.median).toBe(3);expect(r.variance).toBeCloseTo(8/3);expect(r.sample).toBe(4)
  expect(r.slope).toBe(2);expect(r.intercept).toBe(1);expect(r.r2).toBe(1);expect(r.hist.reduce((n,b)=>n+b.n,0)).toBe(3)
})
it('refuses missing or extraneous columns, and bounds degenerate statistics',()=>{
  expect(()=>parseData('0,1\n1,')).toThrow();expect(()=>parseData('1,2,3')).toThrow()
  const r=statistics(parseData('0,3'));expect(r.sample).toBeNull();expect(r.correlation).toBeNull();expect(r.slope).toBeNull()
  expect(statistics([[1,2],[2,2]]).r2).toBeNull()
})
