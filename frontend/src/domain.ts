export type Method = 'analytic' | 'euler' | 'semi_implicit' | 'rk4'
export type Level = 'intro' | 'school' | 'university' | 'research'
export type Status = 'VERIFIED' | 'LIMITED' | 'FAILED' | 'UNSUPPORTED' | 'UNVERIFIED'
export interface Variable {
  key: string
  label: string
  unit: string
  min: number
  max: number
  step: number
  default: number
}
export interface ModelSpec {
  model: string
  title: string
  category: string
  goal: string
  formula: string
  assumptions: string[]
  variables: Variable[]
  methods: Method[]
  measurements: Record<string, string>
  visualization: string
  comparison: string
  objects: string[]
  duration: number
  dt: number
}
export interface Experiment extends ModelSpec {
  id: string
  values: Record<string, number>
  method: Method
}
export interface Run {
  times: number[]
  series: Record<string, number[]>
  status: Status
  checks: { label: string; passed: boolean; detail: string }[]
  facts: Record<string, number>
  convergence: { dt: number; error: number }[]
}
export interface Snapshot {
  experiment: Experiment
  revision: number
  run: Run
  explanation: string
}
export type Classification = 'sufficient' | 'assumptions' | 'needs_clarification' | 'unsupported'
export interface MissingCondition {
  key?: string | null
  label: string
  unit?: string
  reason?: string
}
export interface DialogueState {
  id: string
  original_message: string
  experiment_id: string | null
  revision: number | null
  target_experiment_id?: string | null
  model: string | null
  model_hint: string
  kind?: 'conditions' | 'semantic'
  force_new?: boolean
  turn?: number
  missing_conditions: MissingCondition[]
  followups: string[]
}
export interface ChatResult {
  action: 'create' | 'modify' | 'explain' | 'unsupported' | 'needs_clarification'
  message: string
  snapshot: Snapshot | null
  level: Level
  classification?: Classification
  assumptions?: string[]
  missing_conditions?: MissingCondition[]
  dialogue?: DialogueState | null
}
export interface Patch {
  values: Record<string, number>
  method: Method
  dt: number
  duration: number
}
export const levels: Record<Level, string> = {
  intro: '입문',
  school: '중·고등',
  university: '대학',
  research: '연구',
}
export const methods: Record<Method, string> = {
  analytic: '해석해',
  euler: '오일러',
  semi_implicit: '반암시적 오일러',
  rk4: '룽게–쿠타 4차',
}
export const statuses: Record<Status, string> = {
  VERIFIED: '검증 통과',
  LIMITED: '조건부 검증',
  FAILED: '검증 실패',
  UNSUPPORTED: '미지원',
  UNVERIFIED: '미검증',
}
export const colors = ['#c4ee83', '#8eb8ff', '#f0ad75', '#c49eff']
export const quantities: Record<string, string> = {
  displacement: '원점 변위', quarter_displacement: '¼ 파장 지점 변위', temperature: '온도',
  edge_temperature: '끝점 온도', temperature_rate: '온도 변화율', heat: '받은 열',
  x: '수평 위치',
  y: '높이',
  vx: '수평 속도',
  vy: '수직 속도',
  ax: '수평 가속도',
  ay: '수직 가속도',
  fx: '수평 힘',
  fy: '수직 힘',
  energy: '역학적 에너지',
  ke: '운동 에너지',
  pe: '위치 에너지',
  error: '기준해 오차',
  pressure: '압력',
  depth: '깊이',
  buoyancy: '부력',
  flow: '유량',
  speed: '속력',
  momentum: '운동량',
  volume: '부피',
  area: '단면적',
  weight: '무게',
  support: '지지력',
  gauge_pressure: '게이지압',
  dissipated: '누적 소산 에너지',
  angle: '각도',
  angular_velocity: '각속도',
}
export type RequestBody = Record<string, unknown>
export async function api<T>(path: string, method = 'GET', body?: RequestBody | Blob): Promise<T> {
  const response = await fetch('/api' + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body instanceof Blob ? body : body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    let detail = ''
    try {
      const error = (await response.json()).detail
      if (typeof error === 'string') detail = error
      else if (Array.isArray(error)) detail = error.map((entry) => entry.msg).join(' / ')
    } catch {
      /* Some proxies return a plain-text error page. */
    }
    throw new Error(detail || `실험 서버의 응답을 확인해 주세요 (HTTP ${response.status}).`)
  }
  return response.json() as Promise<T>
}
export function numberText(value: number, digits = 3): string {
  if (!Number.isFinite(value)) return '—'
  if (value !== 0 && (Math.abs(value) < 0.001 || Math.abs(value) >= 1e6))
    return value.toExponential(2)
  return Number(value.toFixed(digits)).toLocaleString('ko-KR', { maximumFractionDigits: digits })
}
export function sampleIndex(times: number[], t: number): number {
  let left = 0,
    right = times.length - 1
  while (left < right) {
    const mid = (left + right + 1) >>> 1
    if (times[mid] <= t) left = mid
    else right = mid - 1
  }
  return left
}
export function range(values: number[], includeZero = false): [number, number] {
  let lo = Infinity,
    hi = -Infinity
  for (const v of values) {
    if (!Number.isFinite(v)) continue
    if (v < lo) lo = v
    if (v > hi) hi = v
  }
  if (lo === Infinity) return [0, 1]
  if (includeZero) {
    lo = Math.min(0, lo)
    hi = Math.max(0, hi)
  }
  if (lo === hi) return lo === 0 ? [-1, 1] : [lo - Math.abs(lo) * 0.1, hi + Math.abs(hi) * 0.1]
  return [lo, hi]
}
export function csv(snapshot: Snapshot): string {
  const { experiment, run } = snapshot
  const keys = Object.keys(run.series)
  const quote = (s: string) => '"' + s.replaceAll('"', '""') + '"'
  const header = [
    quote('t [s]'),
    ...keys.map((key) => {
      const suffix = key.substring(key.indexOf('.') + 1)
      return quote(
        key + (experiment.measurements[suffix] ? ' [' + experiment.measurements[suffix] + ']' : ''),
      )
    }),
  ]
  return (
    '\ufeff' +
    [
      header.join(','),
      ...run.times.map((time, i) => [time, ...keys.map((k) => run.series[k][i] ?? '')].join(',')),
    ].join('\r\n')
  )
}
export function exportCsv(snapshot: Snapshot) {
  const url = URL.createObjectURL(new Blob([csv(snapshot)], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `physis-${snapshot.experiment.model}-r${snapshot.revision}.csv`
  a.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function defaultQuantity(snapshot: Snapshot): string {
  const { experiment, run } = snapshot
  const keys = Object.keys(run.series)
    .filter((k) => k.startsWith('0.'))
    .map((k) => k.slice(2))
  const preferences: Record<string, string[]> = {
    wave_standing: ['quarter_displacement'],
    free_fall: ['y'],
    pendulum: ['x', 'y'],
    hydrostatic: ['pressure'],
    buoyancy: ['buoyancy', 'fy', 'y'],
    continuity: ['flow', 'speed', 'vx'],
  }
  return (
    [...(preferences[experiment.model] ?? []), 'x', 'y', ...keys].find((k) => keys.includes(k)) ??
    'x'
  )
}
export function samples(length: number, limit = 400): number[] {
  if (length <= 0) return []
  const count = Math.min(length, limit)
  return Array.from({ length: count }, (_, i) =>
    count === 1 ? 0 : Math.round((i * (length - 1)) / (count - 1)),
  )
}
