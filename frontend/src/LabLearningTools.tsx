import { useRef, useState, type KeyboardEvent } from 'react'
import { ArrowLeftRight, BookOpen, Ruler } from 'lucide-react'
import type { Method, ModelSpec } from './domain'
import { methods as methodLabels, quantities } from './domain'
import presetRows from './learning-presets.json'
import './lab-learning-tools.css'

export type PresetDefinition = {
  model: string
  title: string
  objective: string
  observations: string[]
  expectedRelation: string
  observationQuestion: string
}

export type LearningQuantity = { key: string; label: string; unit: string }
export type PresetInput = { key: string; label: string; unit: string; value: number }
export type LearningPreset = PresetDefinition & {
  initialValues: Record<string, number>
  initialInputs: PresetInput[]
  quantities: LearningQuantity[]
  assumptions: string[]
  method: Method
  duration: number
  dt: number
}

const presetDefinitions = presetRows as PresetDefinition[]

export function getLearningPresets(catalog: ModelSpec[]): LearningPreset[] {
  const models = new Map(catalog.map((spec) => [spec.model, spec]))
  return presetDefinitions.flatMap((definition) => {
    const spec = models.get(definition.model)
    if (!spec) return []
    return [{
      ...definition,
      initialValues: Object.fromEntries(spec.variables.map((variable) => [variable.key, variable.default])),
      initialInputs: spec.variables.map((variable) => ({
        key: variable.key, label: variable.label, unit: variable.unit, value: variable.default,
      })),
      quantities: definition.observations.flatMap((key) => {
        const unit = spec.measurements[key]
        return unit === undefined ? [] : [{ key, label: quantities[key] ?? key.replaceAll('_', ' '), unit }]
      }),
      assumptions: [...spec.assumptions],
      method: spec.methods[0],
      duration: spec.duration,
      dt: spec.dt,
    }]
  })
}

export type Unit = { id: string; label: string; symbol: string; dimension: string; scale: number; offset?: number }
export type UnitCategory = { id: string; label: string; units: readonly Unit[] }

export const unitCategories = [
  { id: 'length', label: '길이', units: [
    { id: 'meter', label: '미터', symbol: 'm', dimension: 'length', scale: 1 },
    { id: 'kilometer', label: '킬로미터', symbol: 'km', dimension: 'length', scale: 1000 },
    { id: 'centimeter', label: '센티미터', symbol: 'cm', dimension: 'length', scale: .01 },
    { id: 'millimeter', label: '밀리미터', symbol: 'mm', dimension: 'length', scale: .001 },
    { id: 'mile', label: '마일', symbol: 'mi', dimension: 'length', scale: 1609.344 },
    { id: 'foot', label: '피트', symbol: 'ft', dimension: 'length', scale: .3048 },
    { id: 'inch', label: '인치', symbol: 'in', dimension: 'length', scale: .0254 },
  ] },
  { id: 'mass', label: '질량', units: [
    { id: 'kilogram', label: '킬로그램', symbol: 'kg', dimension: 'mass', scale: 1 },
    { id: 'gram', label: '그램', symbol: 'g', dimension: 'mass', scale: .001 },
    { id: 'milligram', label: '밀리그램', symbol: 'mg', dimension: 'mass', scale: .000001 },
    { id: 'tonne', label: '톤', symbol: 't', dimension: 'mass', scale: 1000 },
    { id: 'pound', label: '파운드', symbol: 'lb', dimension: 'mass', scale: .45359237 },
    { id: 'ounce', label: '온스', symbol: 'oz', dimension: 'mass', scale: .028349523125 },
  ] },
  { id: 'time', label: '시간', units: [
    { id: 'second', label: '초', symbol: 's', dimension: 'time', scale: 1 },
    { id: 'millisecond', label: '밀리초', symbol: 'ms', dimension: 'time', scale: .001 },
    { id: 'minute', label: '분', symbol: 'min', dimension: 'time', scale: 60 },
    { id: 'hour', label: '시간', symbol: 'h', dimension: 'time', scale: 3600 },
    { id: 'day', label: '일', symbol: 'd', dimension: 'time', scale: 86400 },
  ] },
  { id: 'speed', label: '속도', units: [
    { id: 'meter-per-second', label: '미터/초', symbol: 'm/s', dimension: 'speed', scale: 1 },
    { id: 'kilometer-per-hour', label: '킬로미터/시간', symbol: 'km/h', dimension: 'speed', scale: 1 / 3.6 },
    { id: 'mile-per-hour', label: '마일/시간', symbol: 'mph', dimension: 'speed', scale: .44704 },
    { id: 'foot-per-second', label: '피트/초', symbol: 'ft/s', dimension: 'speed', scale: .3048 },
    { id: 'knot', label: '노트', symbol: 'kn', dimension: 'speed', scale: 1852 / 3600 },
  ] },
  { id: 'acceleration', label: '가속도', units: [
    { id: 'meter-per-second-squared', label: '미터/초²', symbol: 'm/s²', dimension: 'acceleration', scale: 1 },
    { id: 'centimeter-per-second-squared', label: '센티미터/초²', symbol: 'cm/s²', dimension: 'acceleration', scale: .01 },
    { id: 'foot-per-second-squared', label: '피트/초²', symbol: 'ft/s²', dimension: 'acceleration', scale: .3048 },
    { id: 'standard-gravity', label: '표준 중력', symbol: 'g₀', dimension: 'acceleration', scale: 9.80665 },
  ] },
  { id: 'force', label: '힘', units: [
    { id: 'newton', label: '뉴턴', symbol: 'N', dimension: 'force', scale: 1 },
    { id: 'kilonewton', label: '킬로뉴턴', symbol: 'kN', dimension: 'force', scale: 1000 },
    { id: 'pound-force', label: '파운드힘', symbol: 'lbf', dimension: 'force', scale: 4.4482216152605 },
    { id: 'dyne', label: '다인', symbol: 'dyn', dimension: 'force', scale: .00001 },
  ] },
  { id: 'pressure', label: '압력', units: [
    { id: 'pascal', label: '파스칼', symbol: 'Pa', dimension: 'pressure', scale: 1 },
    { id: 'kilopascal', label: '킬로파스칼', symbol: 'kPa', dimension: 'pressure', scale: 1000 },
    { id: 'megapascal', label: '메가파스칼', symbol: 'MPa', dimension: 'pressure', scale: 1_000_000 },
    { id: 'bar', label: '바', symbol: 'bar', dimension: 'pressure', scale: 100_000 },
    { id: 'atmosphere', label: '기압', symbol: 'atm', dimension: 'pressure', scale: 101_325 },
    { id: 'psi', label: '파운드/제곱인치', symbol: 'psi', dimension: 'pressure', scale: 6894.757293168 },
    { id: 'millimeter-mercury', label: '수은주 밀리미터', symbol: 'mmHg', dimension: 'pressure', scale: 133.322387415 },
  ] },
  { id: 'energy', label: '에너지', units: [
    { id: 'joule', label: '줄', symbol: 'J', dimension: 'energy', scale: 1 },
    { id: 'kilojoule', label: '킬로줄', symbol: 'kJ', dimension: 'energy', scale: 1000 },
    { id: 'calorie', label: '칼로리', symbol: 'cal', dimension: 'energy', scale: 4.184 },
    { id: 'kilocalorie', label: '킬로칼로리', symbol: 'kcal', dimension: 'energy', scale: 4184 },
    { id: 'watt-hour', label: '와트시', symbol: 'Wh', dimension: 'energy', scale: 3600 },
    { id: 'kilowatt-hour', label: '킬로와트시', symbol: 'kWh', dimension: 'energy', scale: 3_600_000 },
    { id: 'electronvolt', label: '전자볼트', symbol: 'eV', dimension: 'energy', scale: 1.602176634e-19 },
  ] },
  { id: 'power', label: '일률', units: [
    { id: 'watt', label: '와트', symbol: 'W', dimension: 'power', scale: 1 },
    { id: 'kilowatt', label: '킬로와트', symbol: 'kW', dimension: 'power', scale: 1000 },
    { id: 'megawatt', label: '메가와트', symbol: 'MW', dimension: 'power', scale: 1_000_000 },
    { id: 'mechanical-horsepower', label: '마력', symbol: 'hp', dimension: 'power', scale: 745.69987158227 },
  ] },
  { id: 'temperature', label: '온도', units: [
    { id: 'kelvin', label: '켈빈', symbol: 'K', dimension: 'temperature', scale: 1 },
    { id: 'celsius', label: '섭씨', symbol: '°C', dimension: 'temperature', scale: 1, offset: 273.15 },
    { id: 'fahrenheit', label: '화씨', symbol: '°F', dimension: 'temperature', scale: 5 / 9, offset: 459.67 * 5 / 9 },
  ] },
  { id: 'density', label: '밀도', units: [
    { id: 'kilogram-per-cubic-meter', label: '킬로그램/미터³', symbol: 'kg/m³', dimension: 'density', scale: 1 },
    { id: 'gram-per-cubic-centimeter', label: '그램/센티미터³', symbol: 'g/cm³', dimension: 'density', scale: 1000 },
    { id: 'gram-per-liter', label: '그램/리터', symbol: 'g/L', dimension: 'density', scale: 1 },
    { id: 'pound-per-cubic-foot', label: '파운드/피트³', symbol: 'lb/ft³', dimension: 'density', scale: 16.01846337396 },
  ] },
  { id: 'angle', label: '각도', units: [
    { id: 'radian', label: '라디안', symbol: 'rad', dimension: 'angle', scale: 1 },
    { id: 'degree', label: '도', symbol: '°', dimension: 'angle', scale: Math.PI / 180 },
    { id: 'gradian', label: '그라디안', symbol: 'gon', dimension: 'angle', scale: Math.PI / 200 },
    { id: 'revolution', label: '회전', symbol: 'rev', dimension: 'angle', scale: 2 * Math.PI },
    { id: 'arcminute', label: '각분', symbol: '′', dimension: 'angle', scale: Math.PI / 10_800 },
  ] },
] as const satisfies readonly UnitCategory[]

const unitLookup = new Map<string, Unit>(unitCategories.flatMap((category) =>
  category.units.map((unit): [string, Unit] => [unit.id, unit])))

export class UnitConversionError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'UnitConversionError'
  }
}

export function convertUnits(value: number, fromId: string, toId: string): number {
  if (!Number.isFinite(value)) throw new UnitConversionError('유한한 숫자를 입력하세요.')
  const from = unitLookup.get(fromId)
  const to = unitLookup.get(toId)
  if (!from || !to) throw new UnitConversionError('등록되지 않은 단위입니다.')
  if (from.dimension !== to.dimension) throw new UnitConversionError('서로 다른 차원의 단위는 변환할 수 없습니다.')
  const baseValue = value * from.scale + (from.offset ?? 0)
  if (from.dimension === 'temperature' && baseValue < -1e-12)
    throw new UnitConversionError('절대 영도보다 낮은 온도는 변환할 수 없습니다.')
  const canonicalValue = from.dimension === 'temperature' ? Math.max(0, baseValue) : baseValue
  const result = (canonicalValue - (to.offset ?? 0)) / to.scale
  if (!Number.isFinite(result)) throw new UnitConversionError('변환 결과가 숫자 범위를 벗어났습니다.')
  return result
}

function TabButton({ id, label, selected, onSelect, onKeyDown, ref }: {
  id: string; label: string; selected: boolean; onSelect: () => void
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void
  ref?: (element: HTMLButtonElement | null) => void
}) {
  return <button ref={ref} id={`lab-tab-${id}`} type="button" role="tab" aria-selected={selected}
    aria-controls={`lab-panel-${id}`} tabIndex={selected ? 0 : -1} onClick={onSelect} onKeyDown={onKeyDown}>{label}</button>
}

export function LabLearningTools({ catalog, onStartPreset }: {
  catalog: ModelSpec[]
  onStartPreset: (preset: LearningPreset) => void
}) {
  const [activeTab, setActiveTab] = useState<'presets' | 'converter'>('presets')
  const tabs = useRef<Array<HTMLButtonElement | null>>([])
  const presets = getLearningPresets(catalog)
  function moveTab(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const tabCount = tabs.current.length
    const next = event.key === 'ArrowRight' ? (index + 1) % tabCount
      : event.key === 'ArrowLeft' ? (index - 1 + tabCount) % tabCount
        : event.key === 'Home' ? 0 : event.key === 'End' ? 1 : -1
    if (next < 0) return
    event.preventDefault()
    const id = next === 0 ? 'presets' : 'converter'
    setActiveTab(id)
    tabs.current[next]?.focus()
  }
  return <section className="lab-learning-tools" aria-label="학습 도구">
    <div className="lab-tool-tabs" role="tablist" aria-label="학습 도구 선택">
      <TabButton id="presets" label="학습 프리셋" selected={activeTab === 'presets'} onSelect={() => setActiveTab('presets')}
        onKeyDown={(event) => moveTab(event, 0)} ref={(element) => { tabs.current[0] = element }} />
      <TabButton id="converter" label="단위 변환" selected={activeTab === 'converter'} onSelect={() => setActiveTab('converter')}
        onKeyDown={(event) => moveTab(event, 1)} ref={(element) => { tabs.current[1] = element }} />
    </div>
    <div id="lab-panel-presets" role="tabpanel" aria-labelledby="lab-tab-presets" hidden={activeTab !== 'presets'}>
      <PresetList presets={presets} onStartPreset={onStartPreset} />
    </div>
    <div id="lab-panel-converter" role="tabpanel" aria-labelledby="lab-tab-converter" hidden={activeTab !== 'converter'}>
      <UnitConverter />
    </div>
  </section>
}

function PresetList({ presets, onStartPreset }: {
  presets: LearningPreset[]; onStartPreset: (preset: LearningPreset) => void
}) {
  if (!presets.length) return <p className="lab-tool-empty">실험 목록을 불러오면 등록된 학습 프리셋이 표시됩니다.</p>
  return <><p className="lab-preset-intro">등록 모델 {presets.length}개의 짧은 탐구 안내입니다. 초기 조건과 가정은 현재 물리 모델 목록에서 가져옵니다.</p>
  <div className="lab-preset-list">
    {presets.map((preset) => <details className="lab-preset-card" key={preset.model}>
      <summary><span className="lab-preset-heading"><b>{preset.title}</b><small>{preset.model.replaceAll('_', ' ')}</small></span>
        <span className="lab-preset-objective">{preset.objective}</span></summary>
      <div className="lab-preset-details">
        <div><h3>관찰할 양</h3><ul className="lab-observation-list">{preset.quantities.map((quantity) =>
          <li key={quantity.key}>{quantity.label} <span>{quantity.unit}</span></li>)}</ul></div>
        <div><h3>예상 관계</h3><p>{preset.expectedRelation}</p></div>
        <div><h3>가정과 범위</h3><ul>{preset.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></div>
        <div><h3>생각해 볼 질문</h3><p>{preset.observationQuestion}</p></div>
        <details className="lab-defaults"><summary>초기 조건 확인</summary>
          <dl>{preset.initialInputs.map((input) => <div key={input.key}><dt>{input.label}</dt>
            <dd>{Number(input.value.toPrecision(8)).toString()} {input.unit}</dd></div>)}</dl>
          <p>계산 방식 {methodLabels[preset.method]} · 관찰 {preset.duration} s · 간격 {preset.dt} s</p>
        </details>
        <button className="lab-start-preset" type="button" onClick={() => onStartPreset(preset)}>이 프리셋으로 실험</button>
      </div>
    </details>)}
  </div></>
}

export function UnitConverter() {
  const [categoryId, setCategoryId] = useState<string>('length')
  const [fromId, setFromId] = useState<string>('meter')
  const [toId, setToId] = useState<string>('kilometer')
  const [input, setInput] = useState('1')
  const category = unitCategories.find((item) => item.id === categoryId) ?? unitCategories[0]
  const from = category.units.find((unit) => unit.id === fromId) ?? category.units[0]
  const to = category.units.find((unit) => unit.id === toId) ?? category.units[1]
  let result: string | null = null
  let error = ''
  if (input.trim()) {
    try {
      const value = convertUnits(Number(input), from.id, to.id)
      result = Number(value.toPrecision(10)).toString()
    } catch (reason) {
      error = reason instanceof Error ? reason.message : '단위를 변환할 수 없습니다.'
    }
  }
  function changeCategory(nextId: string) {
    const next = unitCategories.find((item) => item.id === nextId)
    if (!next) return
    setCategoryId(next.id)
    setFromId(next.units[0].id)
    setToId(next.units[1]?.id ?? next.units[0].id)
  }
  function swap() {
    setFromId(to.id)
    setToId(from.id)
  }
  return <section className="lab-unit-converter" aria-label="단위 변환기">
    <header><div className="lab-tool-icon"><Ruler size={17}/></div><div><h2>단위 변환기</h2><p>실험 선택과 관계없이 사용할 수 있습니다.</p></div></header>
    <label className="lab-category-field">변환할 양
      <select aria-label="변환할 양" value={categoryId} onChange={(event) => changeCategory(event.target.value)}>
        {unitCategories.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select>
    </label>
    <div className="lab-conversion-row">
      <label>입력값
        <input aria-label="입력값" inputMode="decimal" type="number" step="any" value={input} onChange={(event) => setInput(event.target.value)} />
        <select aria-label="입력 단위" value={from.id} onChange={(event) => setFromId(event.target.value)}>
          {category.units.map((unit) => <option key={unit.id} value={unit.id}>{unit.label} ({unit.symbol})</option>)}
        </select>
      </label>
      <button className="lab-swap-units" type="button" aria-label="입력 단위와 변환 단위 바꾸기" onClick={swap}><ArrowLeftRight size={17}/></button>
      <label>변환 결과
        <output aria-live="polite" aria-label="변환 결과">{result ?? '—'}</output>
        <select aria-label="변환 단위" value={to.id} onChange={(event) => setToId(event.target.value)}>
          {category.units.map((unit) => <option key={unit.id} value={unit.id}>{unit.label} ({unit.symbol})</option>)}
        </select>
      </label>
    </div>
    {error && <p className="lab-conversion-error" role="alert">{error}</p>}
    <p className="lab-conversion-note"><BookOpen size={14}/> 변환은 표시 단위만 바꾸며 실험의 계산 입력값은 변경하지 않습니다.</p>
  </section>
}

export default LabLearningTools
