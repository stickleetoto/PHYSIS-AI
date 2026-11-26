import { useState } from 'react'
import {
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  CircleAlert,
  Equal,
  Info,
  ListChecks,
  Settings2,
  SlidersHorizontal,
} from 'lucide-react'
import {
  levels,
  methods,
  numberText,
  statuses,
  type Level,
  type Method,
  type Patch,
  type Snapshot,
} from './domain'

export function Inspector({
  snapshot,
  busy,
  level,
  hidden,
  onPatch,
  onLevel,
  selectedVariable,
}: {
  snapshot: Snapshot
  busy: boolean
  level: Level
  hidden: boolean
  onPatch: (p: Patch) => void
  onLevel: (l: Level) => void
  selectedVariable?:string
}) {
  const { experiment: e, run } = snapshot
  const [tab, setTab] = useState<'inputs' | 'explain' | 'checks'>('inputs')
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(e.values).map(([k, v]) => [k, String(v)])),
  )
  const [method, setMethod] = useState<Method>(e.method)
  const [dt, setDt] = useState(String(e.dt)),
    [duration, setDuration] = useState(String(e.duration))
  const dirty =
    e.variables.some((v) => Number(values[v.key]) !== e.values[v.key] || values[v.key] === '') ||
    method !== e.method ||
    Number(dt) !== e.dt ||
    Number(duration) !== e.duration
  return (
    <aside className="inspector pane" aria-label="실험 설정">
      <header className="panel-heading">
        <h2>
          <SlidersHorizontal size={17} /> 실험 설정
        </h2>
        <span className="micro mono">SI</span>
      </header>
      <div className="tabs inspector-tabs">
        {(
          [
            ['inputs', '실험 조건'],
            ['explain', '해설'],
            ['checks', '검증'],
          ] as const
        ).map(([key, label]) => (
          <button key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'inputs' && (
        <form
          className="inputs"
          onSubmit={(ev) => {
            ev.preventDefault()
            if (!dirty || busy) return
            onPatch({
              values: Object.fromEntries(Object.entries(values).map(([k, v]) => [k, Number(v)])),
              method,
              dt: Number(dt),
              duration: Number(duration),
            })
          }}
        >
          <fieldset disabled={busy}>
            <legend>독립 변수</legend>
            {e.variables.map((v) => (
              <label key={v.key} className={'parameter '+(selectedVariable===v.key?'tutor-variable':'')}>
                <span>
                  {v.label}
                  <code>{variableSymbol[v.key] ?? v.key}</code>
                </span>
                <div className="unit-input">
                  <input
                    aria-label={v.label}
                    type="number"
                    step="any"
                    required
                    min={v.min}
                    max={v.max}
                    value={values[v.key]}
                    onChange={(ev) => setValues({ ...values, [v.key]: ev.target.value })}
                  />
                  <small>{v.unit || '1'}</small>
                </div>
              </label>
            ))}
            <details className="solver">
              <summary>
                <Settings2 size={14} />
                계산 조건
                <ChevronDown size={13} />
              </summary>
              <label>
                계산 방법
                <select
                  aria-label="계산 방법"
                  value={method}
                  onChange={(ev) => setMethod(ev.target.value as Method)}
                >
                  {e.methods.map((m) => (
                    <option key={m} value={m}>
                      {methods[m]}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                시간 간격 Δt (s)
                <input
                  type="number"
                  step="any"
                  required
                  min=".002"
                  max=".2"
                  value={dt}
                  onChange={(ev) => setDt(ev.target.value)}
                />
              </label>
              <label>
                계산 시간 (s)
                <input
                  type="number"
                  step="any"
                  required
                  min=".1"
                  max="30"
                  value={duration}
                  onChange={(ev) => setDuration(ev.target.value)}
                />
              </label>
            </details>
            <button type="submit" className="apply" disabled={!dirty || busy}>
              <Check size={15} />
              변경 적용
            </button>
          </fieldset>
          <div className="formula">
            <h3>
              <Equal size={15} />
              적용 수식
            </h3>
            <p>{e.formula}</p>
          </div>
          <details className="assumptions">
            <summary>
              <Info size={14} />
              모델 가정
              <ChevronDown size={13} />
            </summary>
            <ul>
              {e.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </details>
        </form>
      )}
      {tab === 'explain' && (
        <div className="inspector-body">
          <h3>
            <BookOpen size={16} />
            결과 해설
          </h3>
          <label>
            설명 수준
            <select
              value={level}
              disabled={busy || hidden}
              onChange={(e) => onLevel(e.target.value as Level)}
            >
              {Object.entries(levels).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          {hidden ? (
            <p className="muted">예측을 기록하고 결과를 공개하면 해설을 읽을 수 있습니다.</p>
          ) : (
            <p className="explanation">{snapshot.explanation}</p>
          )}
          <div className="formula">
            <h3>적용 수식</h3>
            <p>{e.formula}</p>
          </div>
          <h3>모델 가정</h3>
          <ul>
            {e.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
      {tab === 'checks' && (
        <div className="inspector-body">
          <h3>
            <ListChecks size={16} />
            물리 검증
          </h3>
          {hidden ? (
            <p className="muted">예측을 기록하고 결과를 공개하면 검증값을 확인할 수 있습니다.</p>
          ) : (
            <>
              <span className={'status ' + run.status.toLowerCase()}>{statuses[run.status]}</span>
              <ul className="checks">
                {run.checks.map((c) => (
                  <li key={c.label}>
                    {c.passed ? (
                      <CheckCheck className="good" size={16} />
                    ) : (
                      <CircleAlert className="warn" size={16} />
                    )}
                    <div>
                      <b>{c.label}</b>
                      <p>{c.detail}</p>
                    </div>
                  </li>
                ))}
              </ul>
              {run.convergence.length > 0 && (
                <>
                  <h3>시간 간격과 최대 오차</h3>
                  <table>
                    <thead>
                      <tr>
                        <th>Δt (s)</th>
                        <th>오차 ({e.measurements.error || 'SI'})</th>
                      </tr>
                    </thead>
                    <tbody>
                      {run.convergence.map((r) => (
                        <tr key={r.dt}>
                          <td>{numberText(r.dt, 5)}</td>
                          <td>{numberText(r.error, 6)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </>
          )}
        </div>
      )}
    </aside>
  )
}
const variableSymbol: Record<string, string> = {
  mass_a: 'mₐ',
  mass_b: 'mᵦ',
  mass: 'm',
  height: 'h',
  g: 'g',
  x0: 'x₀',
  v0: 'v₀',
  a: 'a',
  force: 'F',
  length: 'L',
  angle: 'θ₀',
  radius: 'R',
  k: 'k',
  damping: 'b',
  omega: 'ω',
}
