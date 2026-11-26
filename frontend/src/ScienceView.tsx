import { useEffect, useState, type FormEvent } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { api, colors, methods, numberText, quantities, range, samples, type Method, type Patch, type Snapshot } from './domain'
import './science.css'

interface Card {
  title: string
  latex: string
  steps: string[]
  dimensions: string
  quantity: string
  related: string
  symbols: Record<string, string>
  outputs: string
  source: string
}
interface Props {
  tab: 'formula'|'numerical'
  snapshot: Snapshot
  selectedVariable?: string
  onPatch: (patch: Partial<Patch>) => void
  onModel: (model: string) => void
  onOpenLab?: () => void
}
interface Curve {label: string; x: number[]; y: number[]; color: string}

function Chart({title, lines, xUnit, yUnit}: {title:string; lines:Curve[]; xUnit:string; yUnit:string}) {
  const [xmin,xmax] = range(lines.flatMap(l=>l.x)), [ymin,ymax] = range(lines.flatMap(l=>l.y))
  const px = (x:number) => 83+(x-xmin)/(xmax-xmin)*513
  const py = (y:number) => 157-(y-ymin)/(ymax-ymin)*126
  return <figure className="science-chart">
    <figcaption>{title}</figcaption>
    <svg viewBox="0 0 626 199" role="img" aria-label={title}>
      {[0,.5,1].map(n=><g key={n}><path d={`M83 ${157-n*126}H596`} stroke="#34404b" strokeDasharray="4 4"/>
        <text x="76" y={161-n*126} textAnchor="end">{numberText(ymin+(ymax-ymin)*n)}</text>
        <text x={83+513*n} y="177" textAnchor="middle">{numberText(xmin+(xmax-xmin)*n)}</text></g>)}
      <text x="82" y="16">{yUnit}</text><text x="595" y="195" textAnchor="end">{xUnit}</text>
      {lines.map((line,i)=><g key={line.label}>
        <path d={samples(line.x.length,600).map((idx,j)=>(j?'L':'M')+px(line.x[idx])+','+py(line.y[idx])).join(' ')}
          stroke={line.color} fill="none" strokeWidth={i===0 ? 3.5 : 1.9} strokeDasharray={i ? [undefined,'7 3','3 4','10 4 2 4'][i%4] : undefined}/>
        {line.x.length<=4 && line.x.map((x,j)=><circle key={j} cx={px(x)} cy={py(line.y[j])} r="3" fill={line.color}/>)}</g>)}
    </svg>
    <div className="science-legend">{lines.map(l=><span key={l.label}><i style={{background:l.color}}/>{l.label}</span>)}</div>
  </figure>
}

function Tex({source, display=false}: {source: string; display?:boolean}) {
  return <span className="science-tex" dangerouslySetInnerHTML={{__html:katex.renderToString(source,{
    displayMode:display, output:'htmlAndMathml', throwOnError:true, trust:false, strict:'error',
  })}}/>
}

function highlightSymbol(latex:string, symbol:string) {
  // Treat TeX control words, subscripted variables and text labels as tokens.
  // For example, selecting g must leave the operator name "sgn" intact.
  const tokens = /\\(?:mathrm|text)\{[^{}]*\}|\{\\rm\s+[^{}]*\}|(?:\\[A-Za-z]+|[A-Za-z])(?:_(?:\{[^{}]+\}|[A-Za-z0-9]))?/g
  return latex.replace(tokens,token=>token===symbol ? '\\textcolor{#c1eb83}{'+token+'}' : token)
}

function FormulaView({snapshot, selectedVariable, onPatch, onModel, onOpenLab}: Omit<Props,'tab'>) {
  const [cards,setCards] = useState<Record<string,Card>>({})
  const [issue,setIssue] = useState('')
  const [retry,setRetry] = useState(0)
  useEffect(()=>{
    let active = true
    setIssue('')
    api<Record<string,Card>>('/science/formulas').then(result=>{if(active) setCards(result)})
      .catch(error=>{if(active) setIssue(String(error.message))})
    return ()=>{active=false}
  },[retry])
  const {experiment:e,run} = snapshot, card = cards[e.model]
  const initialKey = selectedVariable && selectedVariable in e.values ? selectedVariable : e.model==='free_fall' ? 'height' : e.variables[0].key
  const [key,setKey] = useState(initialKey)
  useEffect(()=>setKey(initialKey),[e.id,initialKey])
  const variable = e.variables.find(v=>v.key===key) ?? e.variables[0]
  const [draft,setDraft] = useState(String(e.values[variable.key]))
  useEffect(()=>setDraft(String(e.values[variable.key])),[e.id,variable.key,e.values,snapshot.revision])
  const [chosenQuantity,setChosenQuantity] = useState('')
  useEffect(()=>setChosenQuantity(''),[e.id])
  const q = chosenQuantity && run.series['0.'+chosenQuantity] ? chosenQuantity : card?.quantity
  const lines = q ? e.objects.map((label,i)=>({label,color:colors[i%4],x:run.times,y:run.series[i+'.'+q]})).filter(line=>line.y) : []
  function apply(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = Number(draft)
    if(draft.trim() && Number.isFinite(value) && variable.min<=value && value<=variable.max)
      onPatch({values:{[variable.key]:value}})
  }
  return <section className="science-view pane" aria-label="공식 탐구">
    <header className="science-heading"><div><h2>공식 탐구</h2><p>실험 조건과 그래프를 함께 읽어 보세요.</p></div>
      <label>공식 선택 <select aria-label="공식 선택" value={card ? e.model : ''} onChange={ev=>onModel(ev.target.value)}>
        {!card && <option value="">공식 고르기</option>}
        {Object.entries(cards).map(([id,c])=><option key={id} value={id}>{c.title}</option>)}</select></label></header>
    {issue ? <p role="alert">{issue} <button onClick={()=>setRetry(v=>v+1)}>다시 불러오기</button></p> :
      !Object.keys(cards).length ? <p role="status">공식을 불러오는 중입니다.</p> :
      !card ? <div className="science-section"><h3>{e.title}</h3><p>{e.formula}</p><p>단계별 유도를 보려면 위 목록에서 공식을 선택하세요.</p></div> : <>
      <div className="formula-main"><small>{card.title}</small><Tex source={highlightSymbol(card.latex,card.symbols[variable.key])} display/><p>{card.outputs}</p></div>
      <div className="science-columns"><div className="science-section">
        <h3>변수와 단위</h3><div className="science-vars">
          {e.variables.map(v=><button key={v.key} type="button" aria-pressed={v.key===variable.key}
            onClick={()=>setKey(v.key)}><Tex source={card.symbols[v.key]}/><span>{v.label}</span><b>{numberText(e.values[v.key])} {v.unit}</b></button>)}
        </div>
        <form onSubmit={apply} className="science-form"><label>{variable.label} ({variable.unit})
          <input aria-label="공식 변수 값" type="number" min={variable.min} max={variable.max} step="any" required value={draft} onChange={ev=>setDraft(ev.target.value)}/></label>
          <button type="submit" className="science-action">실험에 적용</button></form>
        <small>허용 범위 {numberText(variable.min)} ~ {numberText(variable.max)} {variable.unit}</small>
      </div><div className="science-section"><h3>적용 조건</h3><ul>{e.assumptions.map(a=><li key={a}>{a}</li>)}</ul>
        <h3>차원 분석</h3><p>{card.dimensions}</p></div></div>
      <div className="science-section"><h3>단계별 유도</h3><ol>{card.steps.map(s=><li key={s}>{s}</li>)}</ol>
        <a href={card.source} target="_blank" rel="noreferrer">검증 기준 · OpenStax University Physics ↗</a></div>
      {q && <div className="science-section"><label>공식과 연결된 그래프 <select aria-label="공식 그래프 물리량" value={q} onChange={ev=>setChosenQuantity(ev.target.value)}>
        {Object.keys(e.measurements).map(k=><option key={k} value={k}>{quantities[k]??k} ({e.measurements[k]})</option>)}</select></label>
        <Chart title={(quantities[q]??q)+' · 현재 실험'} lines={lines} xUnit="t (s)" yUnit={e.measurements[q]}/></div>}
      <div className="science-actions">{onOpenLab && <button onClick={onOpenLab}>현재 실험 열기</button>}
        <button onClick={()=>onModel(card.related)}>관련 공식 · {cards[card.related]?.title}</button></div>
    </>}
  </section>
}

interface MethodResult {
  method: Method
  position: number[]
  elapsed_ms:number
  absolute_error:number
  relative_error:number|null
  energy_drift:number
  convergence:{dt:number;error:number}[]
}
interface Comparison {
  values: Record<string,number>
  times:number[]; dt:number; duration:number; amplitude:number; initial_energy:number; rows:MethodResult[]
}
function NumericalView({snapshot}: {snapshot:Snapshot}) {
  const {experiment:e} = snapshot, spring = e.model==='spring'
  const [dt,setDt] = useState(String(spring ? e.dt : .05))
  const [result,setResult] = useState<Comparison|null>(null)
  const [busy,setBusy] = useState(false), [error,setError] = useState('')
  const [request,setRequest] = useState(0)
  const [applied,setApplied] = useState(Number(dt))
  const duration = spring ? e.duration : 6
  useEffect(()=>{
    let active=true
    setBusy(true); setError(''); setResult(null)
    api<Comparison>('/science/numerical','POST',{dt:applied,duration,values:spring ? e.values : {}})
      .then(r=>{if(active)setResult(r)})
      .catch(err=>{if(active)setError(String(err.message))})
      .finally(()=>{if(active)setBusy(false)})
    return ()=>{active=false}
  },[request,applied,duration,spring,e.values])
  function compare(ev:FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setApplied(Number(dt)); setRequest(r=>r+1)
  }
  return <section className="science-view pane" aria-label="수치해석 실험실">
    <header className="science-heading"><div><h2>수치해석 실험실</h2><p>{spring ? '현재 용수철 실험의 질량, 강성, 초기 상태와 관찰 시간을 사용합니다.' : '독립 기준 실험 · 마찰이 없는 용수철의 조화 운동'}</p></div></header>
    <form className="science-form" onSubmit={compare}>
      <label>시간 간격 Δt (s)<input aria-label="수치 실험 시간 간격 (s)" type="number" min={Math.max(.002,duration/4000)} max={Math.min(duration,.2)}
        step="any" required value={dt} onChange={ev=>setDt(ev.target.value)}/></label><button className="science-action" disabled={busy}>계산 방법 비교</button>
    </form>
    {busy && <p role="status">네 가지 방법으로 같은 초기 조건을 계산하고 있습니다.</p>}
    {error && <p role="alert">{error}</p>}
    {result && <>
      <div className="science-section"><h3>계산 방법별 결과</h3>
        <p>m = {result.values.mass} kg · k = {result.values.k} N/m · x₀ = {result.values.x0} m · v₀ = {result.values.v0} m/s · {result.duration} s · Δt = {result.dt} s</p>
        <div className="science-table"><table><thead><tr>{['계산 방법','최대 절대 오차 (m)','상대 오차 (%)','최대 에너지 드리프트 (J)','계산 시간 (ms)'].map(h=><th key={h}>{h}</th>)}</tr></thead>
          <tbody>{result.rows.map(row=><tr key={row.method}><th>{methods[row.method]}</th>
            <td>{numberText(row.absolute_error,5)}</td><td>{row.relative_error===null?'정의되지 않음':numberText(100*row.relative_error,5)}</td>
            <td>{numberText(row.energy_drift,6)}</td><td>{numberText(row.elapsed_ms,5)}</td></tr>)}</tbody></table></div>
        <p>절대 오차는 전체 표본에서 가장 큰 |x − x해석|입니다. 상대 오차는 이를 해석 진폭 {numberText(result.amplitude)} m로 나눈 값입니다. 진폭 0에서는 비율을 정의할 수 없습니다.</p>
        <p>에너지 드리프트는 max |E(t) − E(0)|이며 초기 에너지는 {numberText(result.initial_energy)} J입니다. 계산 시간은 서버에서 각 궤적을 한 번 구한 경과 시간으로, 실행마다 달라집니다.</p>
      </div><div className="science-columns">
        <Chart title="계산 방법별 위치 비교" xUnit="t (s)" yUnit="x (m)" lines={result.rows.map((row,i)=>({label:methods[row.method],x:result.times,y:row.position,color:colors[i]}))}/>
        <Chart title="시간 간격별 최대 위치 오차" xUnit="Δt (s)" yUnit="오차 (m)" lines={result.rows.filter(r=>r.convergence.length).map((r,i)=>({
          label:methods[r.method],color:colors[i+1],x:r.convergence.map(c=>c.dt),y:r.convergence.map(c=>c.error)}))}/>
      </div><p>시간 간격을 줄이면 같은 방정식을 풀 때 생기는 수치 오차가 달라집니다. 용수철의 비선형성이나 공기 저항은 이 모델의 적용 조건에 속합니다.</p>
    </>}
  </section>
}
export function ScienceView(props:Props) {
  return props.tab==='numerical' ? <NumericalView key={props.snapshot.experiment.id+'-'+props.snapshot.revision} snapshot={props.snapshot}/> : <FormulaView {...props}/>
}
