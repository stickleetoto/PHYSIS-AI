import { describe, expect, it } from 'vitest'
import { buildExperimentPngSvgDocument, localizeSvgFragmentUrls } from './pngExport'
import type { Snapshot } from './domain'

const snapshot: Snapshot = {
  revision: 3,
  explanation: '',
  experiment: {
    id: 'fixture',
    model: 'continuity',
    title: '연속 방정식',
    category: '유체',
    goal: '단면적에 따른 속도를 비교합니다.',
    formula: 'A₁v₁ = A₂v₂',
    assumptions: ['정상 흐름', '비압축성 유체'],
    variables: [
      { key: 'area_in', label: '입구 단면적', unit: 'm²', min: 0.01, max: 1, step: 0.01, default: 0.5 },
      { key: 'area_out', label: '출구 단면적', unit: 'm²', min: 0.01, max: 1, step: 0.01, default: 0.25 },
    ],
    methods: ['analytic'],
    method: 'analytic',
    measurements: { speed: 'm/s', flow: 'm³/s' },
    visualization: 'continuity',
    comparison: '',
    objects: ['입구', '출구'],
    duration: 2,
    dt: 0.02,
    values: { area_in: 0.5, area_out: 0.25 },
  },
  run: {
    times: [0, 0.02],
    series: { '0.speed': [1, 1], '1.speed': [2, 2] },
    status: 'LIMITED',
    checks: [
      { label: '유량 보존', passed: true, detail: '두 단면의 유량이 같습니다.' },
      { label: '양의 면적', passed: true, detail: '면적이 양수입니다.' },
    ],
    facts: {},
    convergence: [],
  },
}

describe('experiment PNG SVG document', () => {
  it('includes the current simulation and the experiment evidence metadata', () => {
    const svg = buildExperimentPngSvgDocument(
      '<svg viewBox="0 0 700 278"><path d="M0 0H700"/><circle cx="350" cy="129" r="12"/></svg>',
      { snapshot, kind: 'simulation', displayTitle: '관 안의 흐름', currentTime: 0.02 },
    )

    expect(svg).toContain('<path d="M0 0H700"/>')
    expect(svg).toContain('<circle cx="350" cy="129" r="12"/>')
    expect(svg).toContain('관 안의 흐름')
    expect(svg).toContain('입구 단면적 = 0.5 m²')
    expect(svg).toContain('출구 단면적 = 0.25 m²')
    expect(svg).toContain('정상 흐름')
    expect(svg).toContain('비압축성 유체')
    expect(svg).toContain('조건부 검증')
    expect(svg).toContain('2/2')
    expect(svg).toContain('0.02 s')
  })

  it('labels the graph mode and retains its plotted SVG and selected units', () => {
    const svg = buildExperimentPngSvgDocument(
      '<svg viewBox="0 0 658 157" aria-label="시간에 따른 속력 그래프"><path d="M53 124L633 25" stroke="#c4ee83"/></svg>',
      {
        snapshot,
        kind: 'graph',
        displayTitle: '유속 그래프',
        currentTime: 0.02,
        plotDescription: '시계열 · 속력 (m/s) 대 시간 (s)',
        plotSeries: [{ label: '입구', color: '#c4ee83' }, { label: '출구', color: '#8eb8ff' }],
      },
    )

    expect(svg).toContain('유속 그래프')
    expect(svg).toContain('시계열 · 속력 (m/s) 대 시간 (s)')
    expect(svg).toContain('곡선 및 계열')
    expect(svg).toContain('>입구</text>')
    expect(svg).toContain('>출구</text>')
    expect(svg).toContain('시간에 따른 속력 그래프')
    expect(svg).toContain('stroke="#c4ee83"')
  })

  it('escapes display text before embedding it into the SVG document', () => {
    const svg = buildExperimentPngSvgDocument('<svg viewBox="0 0 1 1"/>', {
      snapshot,
      kind: 'simulation',
      displayTitle: '<script>alert("x")</script>',
    })

    expect(svg).toContain('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;')
    expect(svg).not.toContain('<script>alert')
  })

  it('keeps SVG paint-server references local when copying browser-computed CSS', () => {
    expect(localizeSvgFragmentUrls('url("http://localhost:5173/#fieldGradient")')).toBe('url(#fieldGradient)')
    expect(localizeSvgFragmentUrls('url(#gridPattern)')).toBe('url(#gridPattern)')
  })

  it('wraps long Korean display titles onto additional visible lines', () => {
    const title = '긴 제목'.repeat(16)
    const svg = buildExperimentPngSvgDocument('<svg viewBox="0 0 700 278"/>', {
      snapshot,
      kind: 'simulation',
      displayTitle: title,
    })

    expect(svg).toContain('y="51"')
    expect(svg).toContain('y="89"')
    expect(svg).toContain(`<title>${title}</title>`)
  })
})
