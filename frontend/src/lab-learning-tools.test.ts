import { describe, expect, it } from 'vitest'
import type { ModelSpec } from './domain'
import { convertUnits, getLearningPresets, unitCategories } from './LabLearningTools'

const model = (overrides: Partial<ModelSpec> = {}): ModelSpec => ({
  model: 'spring', title: '용수철의 단순 조화 운동', category: '진동', goal: '주기를 관찰합니다.',
  formula: 'mẍ = −kx', assumptions: ['선형 복원력'],
  variables: [
    { key: 'mass', label: '질량', unit: 'kg', min: .5, max: 20, step: .1, default: 1 },
    { key: 'k', label: '용수철 상수', unit: 'N/m', min: .5, max: 100, step: .5, default: 10 },
  ],
  methods: ['analytic'], measurements: { x: 'm', vx: 'm/s', energy: 'J', pe: 'J' },
  visualization: 'spring', comparison: '주기와 에너지를 비교합니다.', objects: ['물체'], duration: 6, dt: .02,
  ...overrides,
})

describe('education presets', () => {
  it('uses catalog defaults and assumptions for a selected model', () => {
    const [preset] = getLearningPresets([model()])
    expect(preset.model).toBe('spring')
    expect(preset.initialValues).toEqual({ mass: 1, k: 10 })
    expect(preset.initialInputs.map(item => item.value)).toEqual([1, 10])
    expect(preset.assumptions).toEqual(['선형 복원력'])
    expect(preset.method).toBe('analytic')
    expect(preset.duration).toBe(6)
    expect(preset.quantities.every(item => item.key in model().measurements)).toBe(true)
    expect(preset.observationQuestion.length).toBeGreaterThan(5)
  })

  it('does not invent values for models missing from the catalog', () => {
    expect(getLearningPresets([])).toEqual([])
  })
})

describe('independent unit conversion', () => {
  it('exposes all twelve requested dimensions', () => {
    expect(unitCategories.map(item => item.id)).toEqual([
      'length', 'mass', 'time', 'speed', 'acceleration', 'force', 'pressure',
      'energy', 'power', 'temperature', 'density', 'angle',
    ])
  })

  it('converts affine temperature scales correctly', () => {
    expect(convertUnits(32, 'fahrenheit', 'celsius')).toBeCloseTo(0, 10)
    expect(convertUnits(0, 'celsius', 'kelvin')).toBeCloseTo(273.15, 10)
    expect(convertUnits(0, 'celsius', 'fahrenheit')).toBeCloseTo(32, 10)
  })

  it('converts representative units in the registered dimensions', () => {
    expect(convertUnits(1000, 'meter', 'kilometer')).toBeCloseTo(1)
    expect(convertUnits(1, 'atmosphere', 'pascal')).toBeCloseTo(101325)
    expect(convertUnits(1, 'gram-per-cubic-centimeter', 'kilogram-per-cubic-meter')).toBeCloseTo(1000)
  })

  it('rejects incompatible dimensions and temperatures below absolute zero', () => {
    expect(() => convertUnits(1, 'meter', 'kilogram')).toThrow(/차원/)
    expect(() => convertUnits(-300, 'celsius', 'kelvin')).toThrow(/절대 영도/)
  })
})
