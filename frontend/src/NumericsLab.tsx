import {useEffect,useRef,useState, type ReactNode} from 'react'
import {MathPlot} from './MathPlot'
import type {LabResult,Curve} from './mathLabModel'

export function NumericsLab({display,numerical}:{display:(r:LabResult)=>ReactNode;numerical:()=>void}){
  const [expr,X]=useState('x^2-2'),[args,A]=useState({lo:'1',hi:'2',h:'0.1',tolerance:'0.000001',iterations:'32',divisions:'16',reference:''})
  const [result,R]=useState<(LabResult&{traces:Curve[];quadrature:Curve[]})|null>(null),[err,E]=useState(''),[busy,Q]=useState(false)
  const active=useRef<AbortController|null>(null)
  useEffect(()=>()=>{active.current?.abort()},[])
  function clear(){active.current?.abort();active.current=null;R(null);E('');Q(false)}
  async function solve(){
    clear();const ctl=new AbortController();active.current=ctl;Q(true)
    try{
      const values=Object.fromEntries(Object.entries(args).map(([k,v])=>[k,v.trim()?Number(v):null]))
      const r=await fetch('/api/math-lab/numeric',{method:'POST',signal:ctl.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({expression:expr,...values})})
      const body=await r.json()
      if(!r.ok||body.status!=='ok')throw new Error(body.detail??'계산을 마치지 못했습니다.')
      if(active.current===ctl)R(body)
    }catch(e){if(active.current===ctl)E((e as Error).message)}finally{if(active.current===ctl)Q(false)}
  }
  const fields={lo:'첫 초깃값',hi:'둘째 초깃값',h:'차분 간격',tolerance:'잔차 허용 오차',iterations:'최대 반복 수',divisions:'구적 분할 수 (짝수)',reference:'비교할 기준 근 (선택)'}
  return <><div className="ml-work"><div>{result?<><MathPlot curves={result.curves??[]} window={[+args.lo,+args.hi]} title="함수와 근 탐색 반복점"/>
    <MathPlot curves={result.traces} window={[1,Math.max(2,...result.traces.flatMap(c=>c.segments.map(a=>a.length)))]} title="반복 번호에 따른 잔차 |f(x)|"/>
    {result.quadrature.length>0&&<MathPlot curves={result.quadrature} window={[0,+args.divisions]} title="분할 수에 따른 구적 절대 오차"/>}</>:<div className="ml-placeholder">계산하면 근 탐색 경로와 반복별 잔차가 나타납니다.</div>}</div>
    <form className="ml-controls" onSubmit={e=>{e.preventDefault();void solve()}}><label>수치해석 수식<input maxLength={180} value={expr} required onChange={e=>{clear();X(e.target.value)}}/></label>
    {(Object.keys(fields) as (keyof typeof args)[]).map(k=><label key={k}>{fields[k]}<input type="number" required={k!=='reference'}
      min={k==='divisions'?4:k==='iterations'?1:k==='h'?1e-8:k==='tolerance'?1e-12:-1000}
      max={k==='divisions'?64:k==='iterations'?48:k==='h'?100:k==='tolerance'?.1:1000}
      step={k==='divisions'?2:k==='iterations'?1:'any'} value={args[k]} onChange={e=>{clear();A({...args,[k]:e.target.value})}}/></label>)}
    <button disabled={busy}>수치해법 비교</button>{busy&&<button type="button" onClick={clear}>계산 취소</button>}{err&&<p role="alert">{err}</p>}</form></div>
    {result&&<>{display(result)}<div className="ml-panel">{result.steps?.map(s=><p key={s}>{s}</p>)}</div></>}
    <div className="ml-bridge"><p>시간 적분에서는 상태를 한 스텝씩 전진시킵니다. 기존 용수철 수치해석실에서 Euler와 RK4의 궤적을 해석해와 비교하세요.</p><button onClick={numerical}>용수철 시간 적분 비교</button></div></>
}
