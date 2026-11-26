import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { FocusAction } from './bench'
import {
  Axis3d,
  Crosshair,
  Focus,
  Minus,
  Plus,
  Route,
  MoveUpRight,
  ScanLine,
  TrendingUp,
  Download,
} from 'lucide-react'
import { colors, numberText, range, sampleIndex, samples, type Snapshot } from './domain'
import { downloadExperimentPng } from './pngExport'
import './pngExport.css'

type ViewFlags = {
  axes: boolean
  trail: boolean
  force: boolean
  velocity: boolean
  acceleration: boolean
}
const left = 62,
  right = 650,
  top = 45,
  bottom = 238
function ticks(lo: number, hi: number, count: number) {
  const rough = Math.abs(hi - lo) / count
  if (!rough || !Number.isFinite(rough)) return []
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const factor = [1, 2, 5, 10].find((n) => n * magnitude >= rough) ?? 10
  const step = magnitude * factor
  return Array.from(
    { length: Math.max(0, Math.floor(hi / step + 1e-9) - Math.ceil(lo / step - 1e-9) + 1) },
    (_, i) => (Math.ceil(lo / step - 1e-9) + i) * step,
  )
}
function vector(
  x: number,
  y: number,
  dx: number,
  dy: number,
  color: string,
  label: string,
  lane = 0,
) {
  const length = Math.hypot(dx, dy)
  if (length < 0.00001) return null
  const ux = dx / length,
    uy = dy / length
  const sign = ux < 0 || (ux === 0 && uy < 0) ? -1 : 1
  x -= uy * lane * sign
  y += ux * lane * sign
  const start = 17,
    end = start + length
  const endX = x + ux * end,
    endY = y + uy * end
  return (
    <g aria-label={label} stroke={color} fill="none" strokeWidth="2">
      <line x1={x + ux * start} y1={y + uy * start} x2={endX} y2={endY} />
      <path
        d={`M${endX - ux * 6 - uy * 3.5},${endY - uy * 6 + ux * 3.5}L${endX},${endY}l${-ux * 6 + uy * 3.5},${-uy * 6 - ux * 3.5}`}
      />
    </g>
  )
}
export function Scene({ snapshot, index, focus, displayTitle }: { snapshot: Snapshot; index: number; focus?:FocusAction[]; displayTitle?: string }) {
  const [flags, setFlags] = useState<ViewFlags>({
    axes: true,
    trail: true,
    velocity: false,
    force: true,
    acceleration: false,
  })
  const [zoom, setZoom] = useState(1)
  const [exportError, setExportError] = useState('')
  const svgRef = useRef<SVGSVGElement>(null)
  useEffect(()=>{
    if(!focus?.length)return
    setFlags(flags=>({...flags,
      force:flags.force||focus.some(a=>a.op==='show_force'),
      velocity:flags.velocity||focus.some(a=>a.op==='show_velocity'),
      acceleration:flags.acceleration||focus.some(a=>a.op==='show_acceleration')}))
  },[focus])
  function onBody(op:string,index:number) {
    const commands=focus?.filter(a=>a.op===op)??[]
    return !commands.length||commands.some(a=>a.index===index)
  }
  const id = useId().replaceAll(':', '')
  const { experiment: e, run } = snapshot
  const title = displayTitle?.trim() || e.title
  const fall = e.model === 'free_fall'
  const fluid = ['continuity', 'hydrostatic', 'buoyancy'].includes(e.model)
  const scene = useMemo(() => {
    const bodies = e.objects.map((name, i) => ({
      name,
      xs: run.series[i + '.x'] ?? [],
      ys: run.series[i + '.y'] ?? [],
      vxs: run.series[i + '.vx'] ?? [],
      vys: run.series[i + '.vy'] ?? [],
      fxs: run.series[i + '.fx'] ?? [],
      fys: run.series[i + '.fy'] ?? [],
      axs: run.series[i + '.ax'] ?? [],
      ays: run.series[i + '.ay'] ?? [],
    }))
    const [x0, x1] = range(
      bodies.flatMap((b) => b.xs),
      true,
    )
    const ySamples = bodies.flatMap((b) => b.ys)
    if (e.model === 'pendulum') ySamples.push(e.values.length)
    const [y0, y1] = range(ySamples, true)
    const scale = Math.min((right - left) / (x1 - x0), (bottom - top) / (y1 - y0)) * zoom
    const sx = (x: number, i = 0) =>
      fall
        ? left + (right - left) * (i === 0 ? 0.29 : 0.71)
        : (left + right) / 2 + (x - (x1 + x0) / 2) * scale
    const sy = (y: number) =>
      fall
        ? bottom - ((y * (bottom - top)) / Math.max(y1, 0.0001)) * zoom
        : (top + bottom) / 2 - (y - (y1 + y0) / 2) * scale
    const points = samples(run.times.length, 300)
    const exposureIndices = Array.from(
      new Set([0.25, 0.5, 0.75, 1].map((f) => sampleIndex(run.times, (run.times.at(-1) ?? 0) * f))),
    )
    const paths = bodies.map((b, n) =>
      points
        .map(
          (i, j) =>
            (j === 0 ? 'M' : 'L') +
            sx(b.xs[i] ?? 0, n).toFixed(2) +
            ',' +
            sy(b.ys[i] ?? 0).toFixed(2),
        )
        .join(' '),
    )
    const vmax = Math.max(
      1e-12,
      ...bodies.map((b) => Math.max(...b.vxs.map((v, i) => Math.hypot(v, b.vys[i] ?? 0)))),
    )
    const fmax = Math.max(
      1e-12,
      ...bodies.map((b) => Math.max(...b.fxs.map((v, i) => Math.hypot(v, b.fys[i] ?? 0)))),
    )
    const amax = Math.max(
      1e-12,
      ...bodies.map((b) => Math.max(...b.axs.map((v, i) => Math.hypot(v, b.ays[i] ?? 0)))),
    )
    return {
      bodies,
      sx,
      sy,
      paths,
      exposureIndices,
      vmax,
      fmax,
      amax,
      yticks: fall
        ? ticks(0, y1 / zoom, 4)
        : ticks(
            (y0 + y1) / 2 - (bottom - top) / 2 / scale,
            (y0 + y1) / 2 + (bottom - top) / 2 / scale,
            4,
          ),
      xticks: fall
        ? []
        : ticks(
            (x0 + x1) / 2 - (right - left) / 2 / scale,
            (x0 + x1) / 2 + (right - left) / 2 / scale,
            7,
          ),
    }
  }, [e, run, zoom, fall])
  const { sx, sy } = scene
  const toggles = [
    { key: 'trail', title: '궤적', icon: Route },
    { key: 'velocity', title: '속도 벡터', icon: MoveUpRight },
    { key: 'acceleration', title: '가속도 벡터', icon: TrendingUp },
    { key: 'force', title: '힘 벡터', icon: ScanLine },
    { key: 'axes', title: '좌표축', icon: Axis3d },
  ] as const
  const exportPng = () => {
    if (!svgRef.current) return
    setExportError('')
    void downloadExperimentPng(svgRef.current, {
      snapshot,
      kind: 'simulation',
      displayTitle: title,
      currentTime: run.times[index],
    }).catch(() => setExportError('PNG 내보내기에 실패했습니다.'))
  }
  return (
    <section className="scene-card" aria-label="시뮬레이션">
      <div className="scene-toolbar">
        <h2>
          <Crosshair size={16} /> 시뮬레이션
        </h2>
        <div className="view-toggles">
          <button type="button" className="png-export-button" onClick={exportPng} aria-label="시뮬레이션 PNG 내보내기" title="시뮬레이션 PNG 내보내기">
            <Download size={14} /> PNG
          </button>
          {toggles.map(({ key, title, icon: Icon }) => (
            <button
              type="button"
              key={key}
              className={flags[key] ? 'selected' : ''}
              aria-label={title}
              title={title}
              aria-pressed={flags[key]}
              disabled={fluid && key !== 'axes'}
              onClick={() => setFlags({ ...flags, [key]: !flags[key] })}
            >
              <Icon size={15} />
            </button>
          ))}
        </div>
      </div>
      <div className="scene-surface">
        {fluid ? (
          <FluidScene snapshot={snapshot} index={index} axes={flags.axes} zoom={zoom} focus={focus} svgRef={(node) => { svgRef.current = node }} displayTitle={title}/>
        ) : (
          <svg
            ref={svgRef}
            viewBox="0 0 700 278"
            className="world-svg"
            role="img"
            aria-label={title + ' 위치와 궤적'}
          >
            <defs>
              <pattern id={id + 'grid'} width="26" height="26" patternUnits="userSpaceOnUse">
                <path
                  d="M26 0H0V26"
                  fill="none"
                  stroke="#7e9eaf"
                  strokeOpacity=".1"
                  strokeWidth=".7"
                />
              </pattern>
              <pattern id={id + 'ground'} width="8" height="8" patternUnits="userSpaceOnUse">
                <path d="M-2 8L8 -2M6 10l4 -4" stroke="#8296a9" strokeOpacity=".35" />
              </pattern>
              <clipPath id={id + 'clip'}>
                <rect x="42" y="1" width="650" height="254" />
              </clipPath>
              {colors.map((color, i) => (
                <radialGradient id={id + 'ball' + i} key={color} cx="33%" cy="26%" r="86%">
                  <stop stopColor="#f2ffe3" />
                  <stop offset=".22" stopColor={color} />
                  <stop offset=".69" stopColor={color} />
                  <stop offset="1" stopColor={i === 0 ? '#5a893a' : '#416595'} />
                </radialGradient>
              ))}
            </defs>
            <rect width="700" height="278" fill={`url(#${id}grid)`} />
            {flags.axes && (
              <g className="svg-axis">
                {scene.yticks.map((t) => (
                  <g key={t}>
                    <line
                      x1={left - 7}
                      x2={right + 12}
                      y1={sy(t)}
                      y2={sy(t)}
                      stroke="#a4bccc"
                      strokeOpacity=".16"
                      strokeDasharray="2 5"
                    />
                    <text x={left - 13} y={sy(t) + 4} textAnchor="end">
                      {numberText(t, 2)}
                    </text>
                  </g>
                ))}
                <text x="25" y="19">
                  y (m)
                </text>
                {!fall && (
                  <>
                    {scene.xticks.map((t) => (
                      <g key={t}>
                        <line
                          x1={sx(t)}
                          x2={sx(t)}
                          y1="26"
                          y2="242"
                          stroke="#a4bccc"
                          strokeOpacity=".16"
                          strokeDasharray="2 5"
                        />
                        <text x={sx(t)} y="256" textAnchor="middle">
                          {numberText(t, 2)}
                        </text>
                      </g>
                    ))}
                    <text x="647" y="272">
                      x (m)
                    </text>
                  </>
                )}
              </g>
            )}
            {fall && (
              <g>
                <rect
                  x={left}
                  y={bottom + 1}
                  width={right - left}
                  height="9"
                  fill={`url(#${id}ground)`}
                />
                <path d={`M${left} ${bottom}H${right}`} stroke="#86a0ae" strokeWidth="1.4" />
                <text className="svg-axis" x={right} y={bottom + 23} textAnchor="end">
                  지면
                </text>
              </g>
            )}
            <g clipPath={`url(#${id}clip)`}>
              {scene.bodies.map((b, i) => {
                const x = sx(b.xs[index] ?? 0, i),
                  y = sy(b.ys[index] ?? 0)
                const color = colors[i % colors.length],
                  mass = e.values[i === 0 ? 'mass_a' : 'mass_b'] ?? e.values.mass
                const fx = b.fxs[index] ?? 0,
                  fy = b.fys[index] ?? 0,
                  vx = b.vxs[index] ?? 0,
                  vy = b.vys[index] ?? 0
                const ax = b.axs[index] ?? 0,
                  ay = b.ays[index] ?? 0
                const tagX = x > 580 ? x - 31 : x + 30,
                  anchor = x > 580 ? 'end' : 'start'
                const tagY = y < 35 ? y + 28 : y - 11
                return (
                  <g key={b.name}>
                    {focus?.some(a=>a.op==='highlight_object'&&a.index===i)&&
                      <circle aria-label={b.name+' 강조'} cx={x} cy={y} r="24" fill="none" stroke="#fff0ad" strokeWidth="2.5" strokeDasharray="5 3"/>}
                    {flags.trail && (
                      <path
                        d={scene.paths[i]}
                        fill="none"
                        stroke={color}
                        strokeOpacity=".65"
                        strokeWidth={fall ? 1.6 : 2}
                        strokeDasharray="4 6"
                      />
                    )}
                    {flags.trail &&
                      fall &&
                      scene.exposureIndices.map((j) => (
                        <circle
                          key={j}
                          cx={sx(b.xs[j], i)}
                          cy={sy(b.ys[j])}
                          r="4"
                          fill={color}
                          fillOpacity=".18"
                          stroke={color}
                          strokeOpacity=".65"
                        >
                          <title>
                            {numberText(run.times[j])} s · {numberText(b.ys[j])} m
                          </title>
                        </circle>
                      ))}
                    {e.model === 'pendulum' && (
                      <g stroke="#a8b4c2">
                        <line x1={sx(0)} x2={x} y1={sy(e.values.length)} y2={y} />
                        <circle cx={sx(0)} cy={sy(e.values.length)} r="3" fill="#a8b4c2" />
                      </g>
                    )}
                    <circle
                      cx={x}
                      cy={y}
                      r="18"
                      stroke={color}
                      fill={color}
                      fillOpacity=".05"
                      strokeOpacity=".27"
                    />
                    <circle
                      cx={x}
                      cy={y}
                      r="12"
                      stroke={color}
                      fill={`url(#${id}ball${i % colors.length})`}
                    />
                    <text x={tagX} y={tagY} textAnchor={anchor} fill={color} className="body-label">
                      {b.name}
                    </text>
                    {mass !== undefined && (
                      <text x={tagX} y={tagY + 16} textAnchor={anchor} className="body-mass">
                        {numberText(mass)} kg
                      </text>
                    )}
                    {flags.force && onBody('show_force',i) &&
                      vector(
                        x,
                        y,
                        (fx / scene.fmax) * 31,
                        (-fy / scene.fmax) * 31,
                        '#f4b981',
                        '힘 ' + numberText(Math.hypot(fx, fy)) + ' N',
                        -5,
                      )}
                    {flags.velocity && onBody('show_velocity',i) &&
                      vector(
                        x,
                        y,
                        (vx / scene.vmax) * 42,
                        (-vy / scene.vmax) * 42,
                        '#85dedb',
                        '속도 ' + numberText(Math.hypot(vx, vy)) + ' m/s',
                        5,
                      )}
                    {flags.acceleration && onBody('show_acceleration',i) &&
                      vector(
                        x,
                        y,
                        (ax / scene.amax) * 36,
                        (-ay / scene.amax) * 36,
                        '#d3b4ff',
                        '가속도 ' + numberText(Math.hypot(ax, ay)) + ' m/s²',
                      )}
                  </g>
                )
              })}
            </g>
          </svg>
        )}
        <div className="scene-foot">
          <div className="scene-key">
            {!fluid && flags.force && <span className="arrow-key force">↗ 힘</span>}
            {!fluid && flags.velocity && <span className="arrow-key velocity">↗ 속도</span>}
            {!fluid && flags.acceleration && <span className="arrow-key accel">↗ 가속도</span>}
            {fall && <span>가로 간격은 표시용</span>}
          </div>
          <div className="zoom">
            <button
              title="축소"
              aria-label="축소"
              disabled={zoom <= 0.5}
              onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
            >
              <Minus size={13} />
            </button>
            <button
              className="zoom-reset"
              title="기본 배율"
              aria-label="기본 배율"
              onClick={() => setZoom(1)}
            >
              <Focus size={12} />
              {Math.round(zoom * 100)}%
            </button>
            <button
              title="확대"
              aria-label="확대"
              disabled={zoom >= 2}
              onClick={() => setZoom((z) => Math.min(2, z + 0.25))}
            >
              <Plus size={13} />
            </button>
          </div>
        </div>
      </div>
      {exportError && <p className="png-export-error" role="alert">{exportError}</p>}
    </section>
  )
}

function FluidScene({
  snapshot,
  index,
  axes,
  zoom,
  focus,
  svgRef,
  displayTitle,
}: {
  snapshot: Snapshot
  index: number
  axes: boolean
  zoom: number
  focus?: FocusAction[]
  svgRef: (node: SVGSVGElement | null) => void
  displayTitle: string
}) {
  const { experiment: e, run } = snapshot
  const sample = (key: string) => run.series['0.' + key]?.[index]
  const pipe = e.model === 'continuity'
  const area1 = e.values.area_in ?? 1,
    area2 = e.values.area_out ?? 1
  const r1 = 64 * Math.sqrt(area1 / Math.max(area1, area2)),
    r2 = 64 * Math.sqrt(area2 / Math.max(area1, area2))
  const depth = sample('depth') ?? 0
  const maxDepth = e.variables.find((v) => v.key === 'depth')?.max ?? 20
  const gaugePosition = (d: number) => 81 + (d / maxDepth) * 121
  const gaugeY = gaugePosition(depth)
  const forces = [
    { label: '부력', v: sample('buoyancy') ?? 0, color: '#c4ee83' },
    { label: '무게', v: -(sample('weight') ?? 0), color: '#f4b981' },
    { label: '지지력', v: sample('support') ?? 0, color: '#8eb8ff' },
  ]
  const maxForce = Math.max(1e-12, ...forces.map((f) => Math.abs(f.v)))
  return (
    <svg
      ref={svgRef}
      viewBox="0 0 700 278"
      role="img"
      aria-label={displayTitle + ' 유체 모식도'}
      className="world-svg fluid-svg"
    >
      <g transform={`translate(350 129) scale(${zoom}) translate(-350 -129)`}>
        {pipe ? (
          <>
            <path
              d={`M120 ${130 - r1}H246L445 ${130 - r2}H580V${130 + r2}H445L246 ${130 + r1}H120Z`}
              fill="#254559"
              stroke="#84b5cc"
              strokeWidth="2"
            />
            {[0.25, 0.5, 0.75].map((f) => (
              <path
                key={f}
                d={`M126 ${130 + r1 * (2 * f - 1)}H246L445 ${130 + r2 * (2 * f - 1)}H574`}
                fill="none"
                stroke="#83c9dd"
                strokeOpacity=".65"
                strokeDasharray="8 6"
              />
            ))}
            {axes &&
              [0, 1].map((i) => (
                <text
                  key={i}
                  x={i === 0 ? 185 : 520}
                  y="48"
                  textAnchor="middle"
                  className="fluid-reading"
                >
                  {i === 0 ? '입구' : '출구'} · {numberText(run.series[i + '.speed'][index])} m/s
                </text>
              ))}
          </>
        ) : (
          <>
            <path d="M155 52V210H545V52" fill="none" stroke="#8198a8" strokeWidth="3" />
            <rect x="157" y="81" width="386" height="127" fill="#28516a" fillOpacity=".7" />
            <path d="M157 81H543" stroke="#8acdda" strokeWidth="2" strokeDasharray="7 3" />
            {e.model === 'buoyancy' ? (
              <>
                <path d="M282 155h40" stroke="#b3c1c9" strokeWidth="3" />
                <text x="274" y="158" textAnchor="end" className="fluid-reading">
                  고정 지지대
                </text>
                <rect
                  x="321"
                  y="127"
                  width="58"
                  height="58"
                  rx="4"
                  fill="#afcf83"
                  stroke="#d5f4a9"
                  strokeWidth="2"
                />
                {forces.map((f, i) => (
                  <g key={f.label}>
                    {vector(333 + i * 17, 153, 0, (-f.v / maxForce) * 30, f.color, f.label)}
                  </g>
                ))}
              </>
            ) : (
              <>
                {axes &&
                  ticks(0, maxDepth, 4).map((d) => (
                    <g key={d} className="svg-axis">
                      <line
                        x1="146"
                        x2="157"
                        y1={gaugePosition(d)}
                        y2={gaugePosition(d)}
                        stroke="#92abb9"
                      />
                      <text x="139" y={gaugePosition(d) + 4} textAnchor="end">
                        {numberText(d)} m
                      </text>
                    </g>
                  ))}
                <g stroke="#c4ee83">
                  <line x1="350" x2="350" y1="81" y2={gaugeY} strokeDasharray="3 4" />
                  <circle cx="350" cy={gaugeY} r="6" fill="#c4ee83" />
                </g>
                {axes && (
                  <text x="366" y={gaugeY + 5} className="fluid-reading">
                    {numberText(depth)} m
                  </text>
                )}
              </>
            )}
          </>
        )}
        {e.objects.map((name,i)=>focus?.some(a=>a.op==='highlight_object' && a.index===i) &&
          <ellipse key={name} aria-label={name+' 강조'} cx={pipe?(i===0?185:520):350}
            cy={pipe?130:e.model==='buoyancy'?156:gaugeY} rx={pipe?32:e.model==='buoyancy'?48:15}
            ry={pipe?(i===0?r1:r2)+6:e.model==='buoyancy'?45:15} stroke="#ffdc84" strokeWidth="3" fill="none"/>)}
      </g>
      {axes && (
        <text x="28" y="26" className="svg-axis">
          {pipe ? '관 단면 모식도' : '수조 단면 모식도'}
        </text>
      )}
      {e.model === 'buoyancy' ? (
        forces.map((f, i) => (
          <text
            key={f.label}
            x={155 + 195 * i}
            y="246"
            textAnchor="middle"
            fontSize="13"
            fill={f.color}
          >
            {f.label} {numberText(Math.abs(f.v))} N {f.v > 0 ? '↑' : f.v < 0 ? '↓' : ''}
          </text>
        ))
      ) : (
        <text x="350" y="246" textAnchor="middle" className="fluid-reading">
          {pipe
            ? '체적 유량 ' + numberText(sample('flow') ?? 0) + ' m³/s'
            : '절대압 ' + numberText(sample('pressure') ?? 0) + ' Pa'}
        </text>
      )}
    </svg>
  )
}
