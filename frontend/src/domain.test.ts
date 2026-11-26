import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Scene } from './Scene'
import { displayedComparison } from './bench'
import {
  csv,
  defaultQuantity,
  numberText,
  range,
  sampleIndex,
  samples,
  type Snapshot,
} from './domain'

const fall: Snapshot = {
  experiment: {
    id: 'fixture',
    model: 'free_fall',
    title: '두 물체의 자유낙하',
    category: '운동학',
    goal: '',
    formula: '',
    assumptions: [],
    variables: [],
    methods: ['analytic'],
    method: 'analytic',
    visualization: 'free_fall',
    comparison: '',
    objects: ['물체 A', '물체 B'],
    duration: 2,
    dt: 0.02,
    values: {},
    measurements: { y: 'm', vy: 'm/s' },
  },
  revision: 1,
  explanation: '',
  run: {
    times: [0, 0.02, 0.031],
    series: { '0.y': [2, 1, 0], '1.y': [2, 1, 0], '0.vy': [0, -1, -2] },
    status: 'VERIFIED',
    checks: [],
    facts: {},
    convergence: [],
  },
}
describe('recorded experiment samples', () => {
  it('uses actual timestamps for an off-grid impact and clamps outside endpoints', () => {
    expect(
      [-1, 0, 0.019, 0.02, 0.029, 0.031, 3].map((t) => sampleIndex(fall.run.times, t)),
    ).toEqual([0, 0, 0, 1, 1, 2, 2])
  })
  it('exports every object and the exact recorded timestamps and values', () => {
    expect(csv(fall).split('\r\n')).toEqual([
      '\ufeff"t [s]","0.y [m]","1.y [m]","0.vy [m/s]"',
      '0,2,2,0',
      '0.02,1,1,-1',
      '0.031,0,0,-2',
    ])
  })
  it('keeps both endpoints when decimating plotted data', () => {
    const indices = samples(4001)
    expect(indices).toHaveLength(400)
    expect([indices[0], indices.at(-1)]).toEqual([0, 4000])
    expect(samples(1)).toEqual([0])
    expect(samples(0)).toEqual([])
  })
  it('saves only the quantity and object still displayed after a comparison member changes', () => {
    const member = {...fall, experiment:{...fall.experiment,objects:['A'],measurements:{y:'m'}}}
    const shown = displayedComparison([fall,member],fall,{quantity:'vy',object_index:1})
    expect(shown.quantity).toBe('y')
    expect(shown.object_index).toBe(0)
  })
  it('keeps tiny measured errors visible and avoids a zero chart span', () => {
    expect(numberText(0.00000012)).toBe('1.20e-7')
    expect(range([5, 5])).toEqual([4.5, 5.5])
    expect(range([-7, -3], true)).toEqual([-7, 0])
    expect(defaultQuantity(fall)).toBe('y')
  })
  it('moves the pressure gauge down the fixed catalog scale as depth increases', () => {
    function gauge(depth: number) {
      const snapshot: Snapshot = {
        ...fall,
        experiment: {
          ...fall.experiment,
          model: 'hydrostatic',
          objects: ['압력계'],
          variables: [
            { key: 'depth', label: '깊이', unit: 'm', min: 0, max: 20, default: 2, step: 0.1 },
          ],
        },
        run: {
          ...fall.run,
          times: [0],
          series: { '0.depth': [depth], '0.pressure': [101325 + 9810 * depth] },
        },
      }
      const svg = renderToStaticMarkup(createElement(Scene, { snapshot, index: 0 }))
      expect(svg).toContain('20 m')
      return Number(svg.match(/<circle cx="350" cy="([^"]+)"/)?.[1])
    }
    expect(gauge(2)).toBeCloseTo(93.1)
    expect(gauge(10)).toBeCloseTo(141.5)
    expect(gauge(20)).toBeCloseTo(202)
  })
})
