import { useEffect, useMemo, useRef, useState } from 'react'
import type { FocusAction } from './bench'
import { ChartNoAxesCombined, Download, Layers2 } from 'lucide-react'
import {
  colors,
  defaultQuantity,
  numberText,
  quantities,
  range,
  sampleIndex,
  samples,
  type Snapshot,
} from './domain'
import { downloadExperimentPng } from './pngExport'
import './pngExport.css'

type GraphMode = 'series' | 'energy' | 'error' | 'convergence'
interface Line {
  label: string
  x: number[]
  y: number[]
  color: string
  dash?: string
}
export function GraphPanel({
  snapshot,
  previous,
  index,
  onSeek,
  focus,
  displayTitle,
}: {
  snapshot: Snapshot
  previous?: Snapshot
  index: number
  onSeek: (t: number) => void
  focus?: FocusAction[]
  displayTitle?: string
}) {
  const [mode, setMode] = useState<GraphMode>('series')
  const [quantity, setQuantity] = useState(() => defaultQuantity(snapshot))
  const [compare, setCompare] = useState(false)
  const [body, setBody] = useState(0)
  const [exportError, setExportError] = useState('')
  const plotRef = useRef<SVGSVGElement>(null)
  const { experiment: e, run } = snapshot
  const title = displayTitle?.trim() || e.title
  const interval=focus?.find(a=>a.op==='highlight_graph')
  useEffect(()=>{
    const key=focus?.find(a=>a.op==='highlight_graph'||a.op==='highlight_quantity')?.quantity
    if(key&&run.series['0.'+key]){setQuantity(key);setMode('series')}
  },[focus,run])
  const q =
    mode === 'error' || mode === 'convergence' ? 'error' : mode === 'energy' ? 'energy' : quantity
  const unit = e.measurements[q] || ''
  const lines = useMemo(() => {
    const lines: Line[] = []
    if (mode === 'convergence') {
      if (run.convergence.length) {
        const sorted = [...run.convergence].sort((a, b) => a.dt - b.dt)
        lines.push({
          label: '최대 오차',
          x: sorted.map((v) => v.dt),
          y: sorted.map((v) => v.error),
          color: colors[0],
        })
      }
    } else if (mode === 'energy') {
      for (const [i, key] of ['energy', 'ke', 'pe'].entries()) {
        const y = run.series[body + '.' + key]
        if (y) lines.push({ label: quantities[key], x: run.times, y, color: colors[i] })
      }
      const prior = previous?.run.series[body + '.energy']
      if (compare && previous?.experiment.model === e.model && prior)
        lines.push({
          label: '이전 역학적 에너지',
          x: previous.run.times,
          y: prior,
          color: '#d2a5fd',
          dash: '9 3 2 3',
        })
    } else {
      e.objects.forEach((label, i) => {
        const y = run.series[i + '.' + q]
        if (y)
          lines.push({
            label,
            x: run.times,
            y,
            color: colors[i % colors.length],
            dash: i > 0 ? '5 6' : undefined,
          })
      })
      if (compare && previous?.experiment.model === e.model) {
        e.objects.forEach((label, i) => {
          const y = previous.run.series[i + '.' + q]
          if (y)
            lines.push({
              label: '이전 ' + label,
              x: previous.run.times,
              y,
              color: i === 0 ? '#d2a5fd' : '#f7ae8e',
              dash: i === 0 ? '9 3 2 3' : '2 4',
            })
        })
      }
    }
    return lines
  }, [mode, q, run, e, compare, previous, body])
  const [xmin, xmax] = useMemo(() => range(lines.flatMap((l) => l.x)), [lines])
  const [ymin, ymax] = useMemo(() => range(lines.flatMap((l) => l.y)), [lines])
  const sx = (v: number) => 53 + ((v - xmin) / (xmax - xmin)) * 580
  const sy = (v: number) => 124 - ((v - ymin) / (ymax - ymin)) * 99
  const paths = useMemo(
    () =>
      lines.map((l) =>
        samples(l.y.length, 600)
          .map((j, i) => (i ? 'L' : 'M') + sx(l.x[j]).toFixed(2) + ',' + sy(l.y[j]).toFixed(2))
          .join(' '),
      ),
    [lines, xmin, xmax, ymin, ymax],
  )
  const plotDescription = mode === 'series'
    ? `시계열 · ${quantities[q] ?? q} (${unit || '단위 미표기'}) 대 시간 (s)`
    : mode === 'energy'
      ? `에너지 · ${quantities[q] ?? q} (${unit || '단위 미표기'}) 대 시간 (s)`
      : mode === 'error'
        ? `오차 · 기준해와의 오차 (${unit || '단위 미표기'}) 대 시간 (s)`
        : `수렴 · 최대 오차 (${unit || '단위 미표기'}) 대 시간 간격 Δt (s)`
  const exportPng = () => {
    if (!plotRef.current) return
    setExportError('')
    void downloadExperimentPng(plotRef.current, {
      snapshot,
      kind: 'graph',
      displayTitle: title,
      currentTime: run.times[index],
      plotDescription,
      plotSeries: lines.map(({ label, color }) => ({ label, color })),
    }).catch(() => setExportError('PNG 내보내기에 실패했습니다.'))
  }
  const modes: [GraphMode, string][] = [
    ['series', '시계열'],
    ['energy', '에너지'],
    ['error', '오차'],
    ['convergence', '수렴'],
  ]
  return (
    <section className="graph-panel pane" aria-label="측정 그래프">
      <header className="panel-heading">
        <h2>
          <ChartNoAxesCombined size={17} /> 측정 그래프
        </h2>
        <div className="graph-heading-actions">
          <div className="segmented">
            {modes.map(([key, label]) => (
              <button key={key} aria-pressed={mode === key} onClick={() => setMode(key)}>
                {label}
              </button>
            ))}
          </div>
          <button type="button" className="png-export-button" onClick={exportPng} disabled={!lines.length} aria-label="그래프 PNG 내보내기" title="그래프 PNG 내보내기">
            <Download size={14} /> PNG
          </button>
        </div>
      </header>
      <div className="graph-options">
        {mode === 'series' ? (
          <select
            value={quantity}
            aria-label="그래프 물리량"
            onChange={(ev) => setQuantity(ev.target.value)}
          >
            {Object.keys(e.measurements)
              .filter((k) => run.series['0.' + k])
              .map((k) => (
                <option key={k} value={k}>
                  {quantities[k] ?? k} ({e.measurements[k]})
                </option>
              ))}
          </select>
        ) : (
          <b className="graph-quantity">
            {mode === 'energy'
              ? '에너지 변화'
              : mode === 'error'
                ? '기준해와의 오차'
                : '시간 간격별 최대 오차'}{' '}
            {unit && '(' + unit + ')'}
          </b>
        )}
        {mode === 'energy' && e.objects.length > 1 && (
          <select
            aria-label="에너지 물체"
            value={body}
            onChange={(ev) => setBody(Number(ev.target.value))}
          >
            {e.objects.map((o, i) => (
              <option value={i} key={o}>
                {o}
              </option>
            ))}
          </select>
        )}
        {mode !== 'convergence' && previous?.experiment.model === e.model && (
          <button
            className="overlay-button"
            aria-pressed={compare}
            onClick={() => setCompare(!compare)}
          >
            <Layers2 size={13} />
            이전 조건 비교
          </button>
        )}
        <div className="legend">
          {lines.map((l) => (
            <span key={l.label}>
              <svg width="20" height="5" aria-hidden="true">
                <line
                  x1="0"
                  x2="20"
                  y1="2.5"
                  y2="2.5"
                  stroke={l.color}
                  strokeWidth="2"
                  strokeDasharray={l.dash}
                />
              </svg>
              {l.label}
            </span>
          ))}
        </div>
      </div>
      {lines.length ? (
        <svg
          ref={plotRef}
          viewBox="0 0 658 157"
          role="img"
          aria-label={
            mode === 'convergence'
              ? '시간 간격에 따른 수렴 그래프'
              : '시간에 따른 ' + (quantities[q] ?? q) + ' 그래프'
          }
          className="plot-svg"
          onClick={(ev) => {
            if (mode === 'convergence') return
            const node = ev.currentTarget,
              pt = node.createSVGPoint()
            pt.x = ev.clientX
            pt.y = ev.clientY
            const matrix = node.getScreenCTM()
            if (matrix) {
              const local = pt.matrixTransform(matrix.inverse())
              onSeek(
                Math.min(
                  run.times.at(-1) ?? 0,
                  Math.max(0, xmin + ((local.x - 53) / 580) * (xmax - xmin)),
                ),
              )
            }
          }}
        >
          {interval?.start!==undefined&&interval.end!==undefined&&interval.quantity===q&&mode==='series'&&
            <rect aria-label="튜터 강조 구간" x={sx(interval.start)} y="24" width={Math.max(2,sx(interval.end)-sx(interval.start))} height="101" fill="#e4d283" fillOpacity=".20"/>}
          {[0, 0.25, 0.5, 0.75, 1].map((f) => (
            <g key={f}>
              <path
                d={`M53 ${sy(ymin + (ymax - ymin) * f)}H633`}
                stroke="#2b3640"
                strokeDasharray="3 4"
              />
              <text x="46" y={sy(ymin + (ymax - ymin) * f) + 3} textAnchor="end">
                {numberText(ymin + (ymax - ymin) * f, 3)}
              </text>
            </g>
          ))}
          {[0, 0.25, 0.5, 0.75, 1].map((f) => (
            <g key={f}>
              <path d={`M${53 + 580 * f} 25V124`} stroke="#25303a" />
              <text x={53 + 580 * f} y="142" textAnchor="middle">
                {numberText(xmin + (xmax - xmin) * f, 3)}
              </text>
            </g>
          ))}
          <text x="53" y="13">
            {unit}
          </text>
          <text x="645" y="155" textAnchor="end">
            {mode === 'convergence' ? 'Δt (s)' : 't (s)'}
          </text>
          {lines.map((l, i) => (
            <g key={l.label}>
              <path
                d={paths[i]}
                fill="none"
                stroke={l.color}
                strokeWidth={i === 0 ? 3 : 1.8}
                strokeDasharray={l.dash}
                vectorEffect="non-scaling-stroke"
              />
              {mode === 'convergence' &&
                l.x.map((x, j) => (
                  <circle key={x} cx={sx(x)} cy={sy(l.y[j])} r="3.5" fill={l.color} />
                ))}
            </g>
          ))}
          {mode !== 'convergence' && (
            <g>
              <line
                x1={sx(run.times[index])}
                x2={sx(run.times[index])}
                y1="24"
                y2="125"
                stroke="#b6c4d0"
                opacity=".65"
                strokeDasharray="3 3"
              />
              {lines.map(
                (l, i) =>
                  run.times[index] <= (l.x.at(-1) ?? 0) && (
                    <circle
                      key={l.label}
                      cx={sx(run.times[index])}
                      cy={sy(l.y[sampleIndex(l.x, run.times[index])])}
                      r={i === 0 ? 4 : 2.5}
                      fill={l.color}
                    />
                  ),
              )}
            </g>
          )}
        </svg>
      ) : (
        <p className="empty-panel">
          이 모델은{' '}
          {mode === 'convergence'
            ? '시간 간격 수렴도'
            : mode === 'energy'
              ? '에너지 시계열'
              : '이 물리량'}
          를 제공하지 않습니다.
        </p>
      )}
      {exportError && <p className="png-export-error" role="alert">{exportError}</p>}
    </section>
  )
}
