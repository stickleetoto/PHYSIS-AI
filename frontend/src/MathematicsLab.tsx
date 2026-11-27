import {useEffect, useState} from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import type {Level,Snapshot,ModelSpec} from './domain'
import {MathPlot} from './MathPlot'
import {MatrixLab,StatsLab} from './MathDataLabs'
import {NumericsLab} from './NumericsLab'
import {MathOde} from './MathOde'
import {TrigLab, VectorLab, type OpenPhysics} from './MathGeometry'
import {topics,initialInput,bridges,bridgeInput,physicsValues,bridgeDuration,type LabInput,type LabResult,type Topic,type MathEntry,type BridgeId} from './mathLabModel'
import './mathematics.css'

const levels:Record<Level,string>={intro:'입문',school:'중·고등',university:'대학',research:'심화'}
const examples=[
  ['일차','a*x+b'],['이차 · 이동','a*(x-b)^2+c'],['다항','x^3-3*x'],['유리','1/(x-b)'],['무리','sqrt(x-b)'],
  ['절댓값','abs(x-b)'],['지수','exp(a*x)'],['로그','log(x-b)'],['삼각','sin(a*x+b)'],['구간별','piecewise((x^2, x<0), (x+1, True))'],
]
function Tex({source}:{source:string}){
  return <span className="ml-tex" dangerouslySetInnerHTML={{__html:katex.renderToString(source,{throwOnError:false,trust:false,maxExpand:200})}}/>
}
function ResultTable({result}:{result:LabResult}){
  return <dl className="ml-results">{result.rows?.map((r,i)=><div key={i}><dt>{r.label}<small>{r.kind==='exact'?'기호':r.kind==='numeric'?'수치':'판정'}</small></dt>
    <dd>{r.latex?<Tex source={r.latex}/>:r.value}</dd></div>)}</dl>
}

function saveCalculation(input:LabInput,result:LabResult){
  const record={experiment_id:'math.'+input.mode,schema_version:1,input,result}
  const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}))
  const anchor=document.createElement('a')
  anchor.href=url;anchor.download='physis-math-'+input.mode+'.json';anchor.click()
  setTimeout(()=>URL.revokeObjectURL(url),1000)
}

function ExpressionExperiment({seed,bridge,catalog,open}:{seed:LabInput;bridge?:BridgeId;catalog:ModelSpec[];open:OpenPhysics}){
  const [draft,setDraft]=useState(seed),[request,setRequest]=useState<LabInput|null>(seed),[result,setResult]=useState<LabResult|null>(null)
  const [working,setWorking]=useState(true),[applied,setApplied]=useState<LabInput|null>(null)
  const [error,setError]=useState('')
  useEffect(()=>{
    if(!request)return
    let live=true
    const ctl=new AbortController()
    setWorking(true);setError('');setResult(null)
    const timer=setTimeout(async()=>{
      try{
        const {indefinite,...settings}=request
        const payload=indefinite?{...settings,lower:null,upper:null}:settings
        const resp=await fetch('/api/math-lab/calculate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:ctl.signal})
        const body=await resp.json() as LabResult
        if(!live)return
        if(!resp.ok || body.status!=='ok')setError(body.detail??'수식 또는 적용 범위를 확인하세요.')
        else {setResult(body);setApplied(request)}
      }catch(e){if(live)setError(e instanceof Error?e.message:'계산에 실패했습니다.')}
      finally{if(live)setWorking(false)}
    },180)
    return ()=>{live=false;clearTimeout(timer);ctl.abort()}
  },[request])
  function submit(next:LabInput=draft){setRequest({...next});setWorking(true);setResult(null);setError('')}
  function update(next:LabInput,apply=false){setDraft(next);if(apply)submit(next)}
  function stop(){setRequest(null);setWorking(false);setResult(null);setError('계산을 취소했습니다.')}
  const active=Boolean(result&&applied&&JSON.stringify(applied)===JSON.stringify(draft))
  const windowMove=(factor:number,shift:number)=>{
    const width=draft.hi-draft.lo,mid=(draft.hi+draft.lo)/2+width*shift
    const next={...draft,lo:mid-width*factor/2,hi:mid+width*factor/2}
    if(next.hi<=1000&&next.lo>=-1000&&next.hi-next.lo>=1e-5)update(next,true)
  }
  const field=(key:'lo'|'hi'|'point'|'step'|'lower'|'upper'|'divisions',name:string)=><label key={key}>{name}
    <input type="number" aria-label={name} key={String(seed[key])} step={key==='divisions'?1:'any'} min={key==='divisions'?2:-1000} max={key==='divisions'?64:1000}
      value={Number.isFinite(draft[key])?draft[key]:''} onChange={e=>update({...draft,[key]:e.target.valueAsNumber})}/></label>
  const physical=bridge?physicsValues(bridge,draft):null, spec=bridge?catalog.find(m=>m.model===bridges[bridge].model):null
  const duration=bridge?bridgeDuration(bridge,draft):undefined
  const fits=!draft.indefinite&&physical&&spec&&(duration===undefined||(duration>=.1&&duration<=30))&&Object.entries(physical).every(([k,v])=>spec.variables.some(s=>s.key===k&&v>=s.min&&v<=s.max))
  return <><div className="ml-work"><div>
    {active&&applied&&result?<MathPlot curves={result.curves??[]} guides={result.guides} window={[applied.lo,applied.hi]} title={topics[draft.mode].name+' · '+applied.expression}/>:
      <div className="ml-placeholder" role="status">{working?'수식을 계산하고 있습니다.':error||'변경한 입력으로 계산하면 그래프가 표시됩니다.'}</div>}
    <div className="ml-actions"><button onClick={()=>windowMove(1,-.25)}>왼쪽 이동</button><button onClick={()=>windowMove(.5,0)}>확대</button><button onClick={()=>windowMove(2,0)}>축소</button><button onClick={()=>windowMove(1,.25)}>오른쪽 이동</button></div>
    {active&&result&&applied&&<><ResultTable result={result}/><button onClick={()=>saveCalculation(applied,result)}>계산 결과 JSON</button></>}</div>
    <form className="ml-controls" onSubmit={e=>{e.preventDefault();submit()}}>
      <label>함수 예제<select value="" onChange={e=>{if(e.target.value)update({...draft,expression:e.target.value},true)}}><option value="">예제 선택</option>{examples.map(([t,v])=><option key={v} value={v}>{t}</option>)}</select></label>
      <label>수식 f(x)<input aria-label="수식 f(x)" maxLength={180} required value={draft.expression} onChange={e=>update({...draft,expression:e.target.value})}/></label>
      {draft.mode==='function'&&<label>비교 함수 g(x)<input maxLength={180} placeholder="선택 입력" value={draft.other??''} onChange={e=>update({...draft,other:e.target.value||undefined})}/></label>}
      {Object.entries(draft.params).filter(([key])=>new RegExp('\\b'+key+'\\b').test(draft.expression+' '+(draft.other??''))).map(([key,val])=><label key={key}>계수 {key}
        <input aria-label={'계수 '+key} type="number" step="any" min="-1000" max="1000" value={Number.isFinite(val)?val:''} onChange={e=>update({...draft,params:{...draft.params,[key]:e.target.valueAsNumber}})}/>
        <input aria-label={'계수 '+key+' 조절'} type="range" min={Math.min(-10,val||0)} max={Math.max(10,val||0)} step=".1" value={val||0}
          onChange={e=>update({...draft,params:{...draft.params,[key]:+e.target.value}})} onPointerUp={()=>submit()} onKeyUp={()=>submit()}/></label>)}
      <fieldset><legend>그래프 범위</legend>{field('lo','왼쪽 끝')}{field('hi','오른쪽 끝')}</fieldset>
      {draft.mode!=='integral'?<fieldset><legend>관찰 위치</legend>{field('point','기준점 p')}{draft.mode!=='function'&&field('step','간격 h')}</fieldset>:
        <fieldset><legend>적분 조건</legend><label>적분 유형<select aria-label="적분 유형" value={draft.indefinite?'indefinite':'definite'}
          onChange={e=>update({...draft,indefinite:e.target.value==='indefinite'},true)}><option value="definite">정적분 · 근사</option><option value="indefinite">부정적분</option></select></label>
          {!draft.indefinite&&<>{field('lower','적분 시작')}{field('upper','적분 끝')}{field('divisions','분할 수')}</>}</fieldset>}
      <div className="ml-actions"><button className="ml-primary" type="submit">계산하기</button>{working&&<button type="button" onClick={stop}>계산 취소</button>}</div>
      <details><summary>수식 입력 안내</summary><p>곱셈은 *로 표시합니다. 변수 x와 계수 a, b, c, 상수 pi를 사용하세요. 함수는 sin, cos, tan, exp, log, sqrt, abs를 지원합니다. 구간별 문법은 예제에서 확인하세요.</p></details>
    </form></div>
    {active&&result?.steps?.length?<section className="ml-panel"><h3>계산 과정</h3><ol>{result.steps.map((s,i)=><li key={i}>{s}</li>)}</ol></section>:null}
    {bridge&&<section className="ml-bridge"><h3>{bridges[bridge].label}</h3><p>{bridges[bridge].units}</p>
      <button disabled={!fits||!active} onClick={()=>{if(physical)open(bridges[bridge].model,physical,bridges[bridge].label,duration)}}>현재 계수로 물리 실험 열기</button>
      {(!fits||!active)&&<p>연결 예제의 식과 물리 모델의 계수 범위를 확인한 뒤 계산하세요.</p>}</section>}</>
}

export function MathematicsLab({entry,snapshot,catalog,open,numerical}:{entry:MathEntry;snapshot:Snapshot|null;catalog:ModelSpec[];open:OpenPhysics;numerical:()=>void}){
  const [current,setCurrent]=useState(entry),[revision,bump]=useState(0),[level,setLevel]=useState<Level>('school')
  const topic=current.topic,lesson=topics[topic]
  function select(e:MathEntry){setCurrent(e);bump(v=>v+1)}
  return <section className="ml-shell" aria-label="수학 실험실"><aside className="ml-nav"><h2>수학 실험실</h2>
    <nav aria-label="수학 분야">{(['function','limit','derivative','integral','vector','trig','matrix','statistics','numerics','ode'] as Topic[]).map(k=><button key={k} aria-pressed={k===topic} onClick={()=>select({topic:k})}>{topics[k].name}</button>)}</nav>
    <label>학습 수준<select value={level} onChange={e=>setLevel(e.target.value as Level)}>{Object.entries(levels).map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label>
    <h3>물리 연결 예제</h3>{(Object.keys(bridges) as BridgeId[]).map(id=><button key={id} onClick={()=>select({topic:bridges[id].mode,bridge:id,input:bridgeInput(id,snapshot??undefined)})}>{bridges[id].label}</button>)}
    <button onClick={numerical}>운동방정식 · 수치해석실</button>
    </aside><article className="ml-content" data-experiment-id={'math.'+topic}><header><h2>{lesson.name}</h2><p>{lesson.goal}</p></header>
    <div className="ml-law"><Tex source={lesson.law}/><span>{lesson.meaning}</span></div>
    {topic==='ode'?<MathOde display={r=><ResultTable result={r}/>} open={open}/>:topic==='matrix'?<MatrixLab display={r=><ResultTable result={r}/>}/>:topic==='statistics'?<StatsLab snapshot={snapshot}/>:
      topic==='numerics'?<NumericsLab display={r=><ResultTable result={r}/>} numerical={numerical}/>:
      topic==='vector'?<VectorLab key={revision} open={open}/>:topic==='trig'?<TrigLab key={revision} initial={current.trig} open={open} snapshot={snapshot}/>:
      <ExpressionExperiment key={revision} seed={current.input??initialInput(topic)} bridge={current.bridge} catalog={catalog} open={open}/>}
    <section className="ml-panel"><h3>관찰과 확인</h3><p>{lesson.example}</p><p><strong>확인 문제</strong> {lesson.question}</p><p>{lesson.limit}</p>
    {level==='intro'?<p>조건 하나만 바꾸고 처음 그림과 다음 그림을 비교해 보세요.</p>:level==='university'||level==='research'?<p>정의역과 단위를 먼저 적고 위 관계가 성립하는 조건을 설명해 보세요.{level==='research'&&' 경계값에서 성립하지 않는 사례도 구성해 보세요.'}</p>:null}</section>
    </article></section>
}
