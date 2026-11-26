import { useEffect, useRef, useState, type FormEvent } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { api, numberText, range } from './domain'
import './science.css'
import './formula-library.css'

interface Formula {
  formula_id:string; model:string; title:string; latex:string; derivation:string; applicability:string
  conditions:string[]; concepts:string[]; source:{title:string;url:string;section:string}
  variables:{name:string;symbol:string;unit:string;dimension:string;description:string}[]
}
interface Props {onModel:(model:string)=>void; initialTool?:boolean; initialId?:string}

function Tex({value,block=false}:{value:string;block?:boolean}) {
  return <span className="science-tex" dangerouslySetInnerHTML={{__html:katex.renderToString(value,{
    throwOnError:false,trust:false,displayMode:block,output:'htmlAndMathml',maxExpand:200,
  })}}/>
}

const operations = {
  simplify:['대수식 정리','(x+1)^2-x^2',''],
  solve:['방정식 풀이','x^2','4'],
  differentiate:['미분','x^3',''],
  integrate:['부정적분','2*x',''],
  substitute:['변수 대입','x^2+1',''],
  equivalent:['수식 동치성 검사','(x+1)^2','x^2+2*x+1'],
  dimension:['단위·차원 검사','F/m','a'],
  graph:['함수 그래프','sin(x)',''],
  compare_root:['방정식의 수치해·기호해 비교','x^2','2'],
  compare:['정적분 수치해 비교','x^2',''],
} as const
type Op = keyof typeof operations
const domains = {real:'모든 실수',positive:'양의 실수',nonnegative:'0 이상',nonzero:'0 제외'}
const statuses:Record<string,string> = {computed:'계산 결과', verified:'검증 통과',failed:'검증 실패',
  domain_mismatch:'정의역 불일치',unverifiable:'검증 불가능',invalid:'입력 확인'}
type Point = [number,number]
interface Result {status:string;detail?:string;result?:string;latex?:string;domain?:string;domains?:string[];
  numeric?:number;symbolic_value?:number;steps?:number;method?:string;absolute_error?:number;segments?:Point[][]}

function Curve({segments,variable}:{segments:Point[][];variable:string}) {
  const points = segments.flat()
  const [xmin,xmax] = range(points.map(p=>p[0])), [ymin,ymax] = range(points.map(p=>p[1]))
  const px = (x:number) => 84+(x-xmin)/(xmax-xmin)*500
  const py = (y:number) => 175-(y-ymin)/(ymax-ymin)*150
  return <figure className="science-chart"><figcaption>함수 그래프</figcaption><svg viewBox="0 0 620 220" role="img" aria-label={variable+'에 따른 함수값'}>
    {[0,.5,1].map(n=><g key={n}><path d={['M84',175-n*150,'H584'].join(' ')} stroke="#41515b" strokeDasharray="4 4"/>
      <text x="77" y={179-n*150} textAnchor="end">{numberText(ymin+n*(ymax-ymin))}</text>
      <text x={84+n*500} y="197" textAnchor="middle">{numberText(xmin+n*(xmax-xmin))}</text></g>)}
    <text x="84" y="17">f({variable})</text><text x="584" y="217">{variable}</text>
    {segments.map((s,i)=>s.length===1 ? <circle key={i} cx={px(s[0][0])} cy={py(s[0][1])} r="3" fill="#c1eb83"/> :
      <polyline key={i} points={s.map(([x,y])=>px(x)+','+py(y)).join(' ')} fill="none" stroke="#c1eb83" strokeWidth="2.5"/>)}
  </svg></figure>
}

function pairs(input:string,numeric:boolean) {
  const result:Record<string,string|number> = {}
  for (const term of input.split(',').map(v=>v.trim()).filter(Boolean)) {
    const parts = term.split('=').map(v=>v.trim())
    if(parts.length!==2 || !/^[A-Za-z][A-Za-z0-9_]{0,15}$/.test(parts[0]) || !parts[1] || Object.hasOwn(result,parts[0]))
      throw new Error('변수=값 형식으로 입력하고 여러 항목은 쉼표로 구분하세요.')
    const value = numeric ? Number(parts[1]) : parts[1]
    if(numeric && !Number.isFinite(value)) throw new Error('유한한 수를 입력하세요.')
    result[parts[0]]=value
  }
  return result
}

function MathTool({units}:{units:string[]}) {
  const [operation,setOperation] = useState<Op>('simplify')
  const [expr,setExpr] = useState<string>(operations.simplify[1]), [other,setOther] = useState('')
  const [v,setV] = useState('x'), [sub,setSub] = useState(''), [unitInput,setUnits] = useState('F=N, m=kg, a=m/s²')
  const [domain,setDomain] = useState('real'), [otherDomain,setOtherDomain] = useState('real')
  const [lo,setLo] = useState('-2'), [hi,setHi] = useState('2')
  const [result,setResult] = useState<Result|null>(null), [error,setError] = useState(''), [busy,setBusy] = useState(false)
  const [usedVariable,setUsedVariable] = useState('x')
  const latest = useRef(0)
  useEffect(()=>()=>{latest.current++},[])
  function select(op:Op) {
    setOperation(op);setExpr(operations[op][1]);setOther(operations[op][2]);setSub(op==='substitute'?'x=2':'')
    setV('x');setLo(op==='compare_root'?'0':'-2');setHi('2');setDomain('real');setOtherDomain('real');setResult(null);setError('')
  }
  async function run(ev:FormEvent) {
    ev.preventDefault()
    const request = ++latest.current
    setError('');setResult(null);setBusy(true)
    try {
      const reply = await api<Result>('/math','POST',{operation,expression:expr,
        other:two && other.trim()?other:null,variable:v,domain,other_domain:two?otherDomain:null,
        values:operation==='dimension'?{}:pairs(sub,true),units:operation==='dimension'?pairs(unitInput,false):{},
        lower:Number(lo),upper:Number(hi)})
      if(latest.current===request){setResult(reply);setUsedVariable(v)}
    } catch(e) {if(latest.current===request)setError((e as Error).message)}
    finally {if(latest.current===request)setBusy(false)}
  }
  const two = ['solve','dimension','equivalent','compare_root'].includes(operation)
  return <section className="science-section formula-math" aria-label="기호 수학 도구"><h3>기호 수학 도구</h3>
    <form onSubmit={run}><fieldset disabled={busy}>
      <label>연산<select aria-label="연산" value={operation} onChange={e=>select(e.target.value as Op)}>
        {Object.entries(operations).map(([key,[name]])=><option key={key} value={key}>{name}</option>)}</select></label>
      <label>{two?'왼쪽 식':'입력 수식'}<input value={expr} maxLength={180} required onChange={e=>setExpr(e.target.value)}/></label>
      {two && <label>{operation==='dimension'?'비교할 오른쪽 식 (선택)':'오른쪽 식'}
        <input value={other} required={operation!=='dimension'} maxLength={180} onChange={e=>setOther(e.target.value)}/></label>}
      {operation==='dimension' ? <label>변수별 SI 단위<input value={unitInput} onChange={e=>setUnits(e.target.value)}/>
        <small>{units.join(' · ')}</small></label> : <>
        <label>기준 변수<input value={v} maxLength={16} required pattern="[A-Za-z][A-Za-z0-9_]*" onChange={e=>setV(e.target.value)}/></label>
        <label>{two?'왼쪽 정의역':'기준 변수의 정의역'}<select value={domain} onChange={e=>setDomain(e.target.value)}>
          {Object.entries(domains).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>
        {two && <label>오른쪽 정의역<select value={otherDomain} onChange={e=>setOtherDomain(e.target.value)}>
          {Object.entries(domains).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>}
        <label>변수 대입값 {operation==='substitute'?'':'(선택)'}<input placeholder="a=2, b=3" value={sub}
          required={operation==='substitute'} onChange={e=>setSub(e.target.value)}/></label>
      </>}
      {['graph','compare','compare_root'].includes(operation) && <>
        <label>구간 시작<input type="number" step="any" required value={lo} onChange={e=>setLo(e.target.value)}/></label>
        <label>구간 끝<input type="number" step="any" required value={hi} onChange={e=>setHi(e.target.value)}/></label></>}
      <button className="science-action">{busy?'계산 중…':'계산하기'}</button>
    </fieldset></form>
    <p>곱셈은 *로, 정수 거듭제곱은 ^로 씁니다. sin, cos, sqrt, exp, log, abs, pi를 지원합니다.</p>
    {error && <p role="alert">{error}</p>}
    {result && <div aria-live="polite" className="formula-result"><h3>{statuses[result.status]??result.status}</h3>
      {result.latex?<Tex value={result.latex} block/>:result.result && <p>{result.result}</p>}
      {result.detail && <p>{result.detail}</p>}{result.domain && <p>정의역 · {result.domain}</p>}
      {result.domains && <p>왼쪽 정의역 · {result.domains[0]}<br/>오른쪽 정의역 · {result.domains[1]}</p>}
      {result.numeric!==undefined && <p>{result.method==='bisection'?'이분법 '+result.steps+'회':'사다리꼴 '+result.steps+'구간'} · {numberText(result.numeric,8)}<br/>
        기호해의 수치값 · {numberText(result.symbolic_value!,8)}<br/>절대오차 · {numberText(result.absolute_error!,8)}</p>}
      {result.segments && <Curve segments={result.segments} variable={usedVariable}/>}
    </div>}
  </section>
}

export default function FormulaLibrary({onModel,initialTool=false,initialId}:Props) {
  const [data,setData] = useState<{items:Formula[];units:string[]}|null>(null)
  const [error,setError] = useState(''), [reload,setReload] = useState(0)
  const [query,setQuery] = useState(''), [id,setId] = useState(initialId??'newton'), [tool,setTool] = useState(initialTool)
  useEffect(()=>{setTool(initialTool)},[initialTool])
  useEffect(()=>{if(initialId){setId(initialId);setQuery('');setTool(false)}},[initialId])
  useEffect(()=>{
    let active=true
    setError('')
    api<{items:Formula[];units:string[]}>('/formulas').then(r=>{if(active)setData(r)})
      .catch(e=>{if(active)setError(e.message)})
    return ()=>{active=false}
  },[reload])
  const matches=(data?.items??[]).filter(r=>query.trim().toLowerCase().split(/\s+/).every(t=>
    [r.title,r.formula_id,r.latex,...r.concepts,...r.conditions,...r.variables.map(v=>v.name+' '+v.description)].join(' ').toLowerCase().includes(t)))
  const card=matches.find(r=>r.formula_id===id)??matches[0]
  return <section className="science-view pane formula-library" aria-label="공식 라이브러리">
    <header className="science-heading"><h2>공식 라이브러리</h2><div className="science-actions">
      <button aria-pressed={!tool} onClick={()=>setTool(false)}>공식 목록</button><button aria-pressed={tool} onClick={()=>setTool(true)}>기호 수학 도구</button></div></header>
    {tool ? <MathTool units={data?.units??[]}/> : <>
      {error && <p role="alert">{error} <button onClick={()=>setReload(n=>n+1)}>다시 불러오기</button></p>}
      {!error && !data && <p role="status">공식을 불러오고 있습니다.</p>}
      {data && <><div className="science-form"><label>공식 검색<input type="search" placeholder="공식 이름, 개념, 기호" value={query} onChange={e=>setQuery(e.target.value)}/></label>
        <label>공식 선택<select aria-label="공식 선택" value={card?.formula_id??''} onChange={e=>setId(e.target.value)}>
          {!matches.length && <option value="">검색 결과 없음</option>}
          {matches.map(r=><option key={r.formula_id} value={r.formula_id}>{r.title}</option>)}</select></label>
        <span>{matches.length}개 공식</span></div>
        {card && <><div className="formula-main"><small>{card.concepts.join(' · ')}</small><h3>{card.title}</h3><Tex value={card.latex} block/>
          <p>{card.applicability==='approximation'?'근사식':'등록된 모형 관계식'} · 출처 대조 및 엔진 수치 검사</p></div>
          <div className="science-columns"><section className="science-section"><h3>변수와 차원</h3>
            <div className="science-table"><table><thead><tr>{['변수','의미','SI 단위','차원'].map(h=><th key={h}>{h}</th>)}</tr></thead>
              <tbody>{card.variables.map(v=><tr key={v.name}><th><Tex value={v.symbol}/></th><td>{v.description}</td><td>{v.unit}</td><td>{v.dimension}</td></tr>)}</tbody></table></div>
            <small>L 길이 · M 질량 · T 시간 · Θ 온도 · N 물질량 · 1 무차원</small>
          </section><section className="science-section"><h3>적용 조건</h3><ul>{card.conditions.map(c=><li key={c}>{c}</li>)}</ul>
            <h3>유도 과정</h3><p>{card.derivation}</p><a href={card.source.url} target="_blank" rel="noreferrer">{card.source.title} · {card.source.section} ↗</a></section></div>
          <div className="science-actions"><button onClick={()=>onModel(card.model)}>관련 실험 실행</button></div></>}
      </>}
    </>}
  </section>
}
