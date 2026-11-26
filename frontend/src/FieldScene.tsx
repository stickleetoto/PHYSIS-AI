import { Waves } from 'lucide-react'
import type { FocusAction } from './bench'
import { colors, numberText, type Snapshot } from './domain'
import './science.css'

const fieldModels = [
  'wave_transverse', 'wave_longitudinal', 'wave_superposition', 'wave_standing',
  'ideal_gas', 'heat_equilibrium', 'cooling', 'heat_diffusion', 'bernoulli', 'fluid_tracer',
]
export const isFieldModel = (model: string) => fieldModels.includes(model)

export function FieldScene({snapshot, index, focus=[]}: {snapshot: Snapshot; index: number; focus?:FocusAction[]}) {
  const {experiment: e, run} = snapshot
  const p = e.values
  const get = (key: string, object = 0) => run.series[object + '.' + key]?.[index]
  if (!run.times.length || index < 0 || index >= run.times.length) return <p>이 시각의 측정 표본이 없습니다.</p>
  const text = (value: number, unit: string) => numberText(value) + ' ' + unit
  const outline = (obj:number,x:number,y:number,width:number,height:number) =>
    focus.some(a=>a.op==='highlight_object' && a.index===obj) &&
      <rect aria-label={e.objects[obj]+' 강조'} x={x} y={y} width={width} height={height} rx="6"
        fill="none" stroke={colors[0]} strokeDasharray="5 3" strokeWidth="2.5"/>
  let drawing
  let caption = ''
  if (e.model.startsWith('wave_')) {
    const origin = get('displacement'), quarter = get('quarter_displacement')
    const phase = (f: number) => f * 4 * Math.PI
    const displacement = (f: number) => origin * Math.cos(phase(f)) + quarter * Math.sin(phase(f))
    const longitudinal = e.model === 'wave_longitudinal'
    // Use a fixed transverse scale across variable edits. Longitudinal offsets
    // use the same horizontal metric as the two-wavelength observation window.
    const px = (f: number) => 55 + 540*f + (longitudinal ? displacement(f)*270/p.wavelength : 0)
    const py = (f: number) => longitudinal ? 105 : 105 - displacement(f)*870
    const path = Array.from({length: 201}, (_, i) => (i ? 'L' : 'M') + px(i/200) + ',' + py(i/200)).join(' ')
    caption = longitudinal ? '점을 따라가면 입자가 앞뒤로 진동하며, 조밀한 구간은 오른쪽으로 이동합니다.' :
      e.model === 'wave_standing' ? '고정된 마디 사이에서 배의 변위가 변합니다.' : '밝은 점은 같은 매질 입자입니다. 파형이 이동하는 동안 입자는 위아래로 진동합니다.'
    drawing = <>
      <path d="M55 105H595" stroke="#56677a" strokeDasharray="3 5" />
      {!longitudinal && <path data-testid="field-wave" d={path} stroke={colors[1]} fill="none" strokeWidth="2.4" />}
      {Array.from({length: 49}, (_, i) => <circle data-testid={i === 6 ? 'field-probe' : undefined}
        key={i} cx={px(i/48)} cy={py(i/48)} r={i === 6 ? 6 : 3.1} fill={i === 6 ? colors[0] : colors[1]} />)}
      <text x="55" y="191">0 m</text><text x="595" y="191" textAnchor="end">{text(2*p.wavelength,'m')}</text>
      {outline(0,px(.125)-12,py(.125)-12,24,24)}
      <text x="325" y="31" textAnchor="middle">{'λ/4 지점 변위  ' + text(quarter,'m')}</text>
    </>
  } else if (e.model === 'heat_diffusion') {
    const base = get('edge_temperature'), excess = get('temperature')-base
    const temperature = (f: number) => base + Math.sin(Math.PI*f)*excess
    const scale = (v: number) => 'hsl(' + Math.max(0, Math.min(230, 225-(v-250)*1.5)) + ' 68% 64%)'
    caption = '색은 국소 온도를 나타냅니다. 양 끝 온도는 고정되어 있습니다.'
    drawing = <>
      {Array.from({length: 90}, (_, i) => <rect key={i} x={55+6*i} y="82" width="6.5" height="40" fill={scale(temperature((i+.5)/90))}/>)}
      {[0,.5,1].map(f=><g key={f}><text x={55+540*f} y="62" textAnchor="middle">{text(temperature(f),'K')}</text>
        <text x={55+540*f} y="157" textAnchor="middle">{text(p.length*f,'m')}</text></g>)}
      {outline(0,309,77,32,50)}
    </>
  } else if (e.model === 'fluid_tracer') {
    const xs = run.series['0.x'], end = Math.max(1, xs[xs.length-1])
    const x = get('x')
    caption = '직선 관의 일정한 축방향 흐름을 따라가는 표지 입자의 위치입니다.'
    drawing = <>
      <rect x="48" y="64" width="554" height="75" rx="5" fill="#264659" stroke="#648ca0"/>
      <path d="M48 101H602" stroke="#8fadb9" strokeDasharray="6 8"/>
      <circle cx={55+540*x/end} cy="101" r="9" fill={colors[0]} data-testid="field-probe"/>
      {outline(0,55+540*x/end-15,86,30,30)}
      <text x="325" y="38" textAnchor="middle">{'x = '+text(x,'m')}</text>
      <text x="55" y="172">0 m</text><text x="595" y="172" textAnchor="end">{text(end,'m')}</text>
    </>
  } else if (e.model === 'bernoulli') {
    const h1 = Math.sqrt(p.area_in)*155, h2 = Math.sqrt(p.area_out)*155
    caption = '수평 유선의 두 단면에서 정압과 유속을 읽습니다. 관은 개념적 단면도입니다.'
    drawing = <>
      <path d={`M65 ${104-h1}H235L405 ${104-h2}H585V${104+h2}H405L235 ${104+h1}H65Z`} fill="#284e63" stroke="#79adc2" strokeWidth="2"/>
      {[0,1].map(i=><g key={i}><text x={i ? 490 : 160} y="47" textAnchor="middle">{(i ? '출구 ' : '입구 ')+text(get('pressure',i)/1000,'kPa')}</text>
        {outline(i,i ? 408 : 78,28,164,122)}
        <text x={i ? 490 : 160} y="109" textAnchor="middle">{text(get('speed',i),'m/s')} →</text></g>)}
    </>
  } else if (e.model === 'ideal_gas') {
    const width = 45 + p.volume*3200
    caption = '상자 폭은 설정 부피를 나타냅니다. 측정값은 평형 상태의 절대압입니다.'
    drawing = <><rect x={(650-width)/2} y="45" width={width} height="91" fill="#254454" stroke={colors[1]}/>
      {outline(0,(650-width)/2-5,40,width+10,101)}
      <text x="325" y="95" textAnchor="middle">{text(get('pressure')/1000,'kPa')}</text>
      <text x="325" y="168" textAnchor="middle">{text(get('temperature'),'K')} · {text(get('volume'),'m³')}</text></>
  } else {
    const both = e.model === 'heat_equilibrium'
    const scope = both ? [[e.objects[0],get('temperature')],[e.objects[1],get('temperature',1)]] as const :
      [['물체',get('temperature')],['주변',p.ambient]] as const
    caption = both ? '물체별 열용량에 따라 같은 양의 열을 주고받아도 온도 변화량은 달라집니다.' : '주변은 온도가 일정한 열저장고입니다.'
    drawing = <>{scope.map(([label,temp],i)=>{
      const x=120+i*265, w = Math.max(0, Math.min(140,(temp-220)*.70))
      return <g key={label}><text x={x} y="58">{label}</text><rect x={x} y="82" width="140" height="25" rx="4" fill="#344654"/>
        {outline(i,x-10,40,160,115)}
        <rect x={x} y="82" width={w} height="25" rx="4" fill={i ? colors[1] : colors[2]}/>
        <text x={x} y="142">{text(temp,'K')}</text></g>})}</>
  }
  return <section className="pane science-field" aria-label="계산된 물리장">
    <header className="panel-heading"><h2><Waves size={17}/> 실험 장면</h2><span>{text(run.times[index],'s')}</span></header>
    <svg role="img" aria-label={e.title+' 계산 모식도'} viewBox="0 0 650 205">{drawing}</svg>
    <p>{caption}</p>
  </section>
}
