import {useRef,useState,useEffect, type ReactNode} from 'react'
import type {LabResult} from './mathLabModel'
import {MathPlot} from './MathPlot'
import type {OpenPhysics} from './MathGeometry'

export function MathOde({open,display}:{open:OpenPhysics;display:(r:LabResult)=>ReactNode}){
  const [model,M]=useState('exponential'),[args,A]=useState({coefficient:-.5,mass:1,k:4,damping:.5,x0:1,v0:0,duration:3,steps:60})
  const [result,R]=useState<(LabResult&{field:number[][]})|null>(null),[err,E]=useState(''),[busy,Q]=useState(false)
  const ref=useRef<AbortController|null>(null)
  useEffect(()=>()=>{ref.current?.abort()},[])
  function clear(){ref.current?.abort();ref.current=null;Q(false);R(null);E('')}
  async function calc(){
    clear();const c=new AbortController();ref.current=c;Q(true)
    try{const resp=await fetch('/api/math-lab/ode',{method:'POST',signal:c.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({model,...args})}),body=await resp.json()
      if(!resp.ok)throw new Error(body.detail)
      if(ref.current===c)R(body)
    }catch(e){if(ref.current===c)E((e as Error).message)}finally{if(ref.current===c)Q(false)}
  }
  const labels={coefficient:'증가·감쇠율 r',mass:'질량 m (kg)',k:'용수철 상수 k (N/m)',damping:'감쇠 계수 b (N·s/m)',x0:'초기값',v0:'초기 속도 (m/s)',duration:'관찰 시간 (s)',steps:'시간 분할 수'}
  return <><div className="ml-work"><div>{result?<><MathPlot title="초기값 문제 · 시간별 해" curves={result.curves??[]} window={[0,args.duration]}/>
    <figure className="ml-chart"><figcaption>{model==='exponential'?'방향장 · 가로 t, 세로 y':'위상 평면 · 가로 위치, 세로 속도'}</figcaption>
    <svg viewBox="-2.4 -2.4 4.8 4.8" style={{height:210}} role="img" aria-label="방향장"><g transform="scale(1,-1)"><path d="M-2.2 0H2.2 M0 -2.2V2.2" stroke="#73878c" strokeWidth=".013"/>
    {result.field.map(([x,y,dx,dy],i)=><g key={i}><path d={'M'+(x-.14*dx)+' '+(y-.14*dy)+'l'+(.28*dx)+' '+(.28*dy)} stroke="#96ccd7" strokeWidth=".025"/><circle cx={x+.14*dx} cy={y+.14*dy} r=".036" fill="#c3e898"/></g>)}</g></svg></figure></>:<p className="ml-placeholder">초기 조건을 선택하고 시간별 해를 계산하세요.</p>}</div>
    <form className="ml-controls" onSubmit={e=>{e.preventDefault();void calc()}}><label>미분방정식<select aria-label="미분방정식" value={model} onChange={e=>{clear();M(e.target.value)}}><option value="exponential">지수 증가·감소</option><option value="spring">선형 용수철</option><option value="damped">감쇠 진동</option></select></label>
    {(Object.keys(args) as (keyof typeof args)[]).filter(k=>model==='exponential'?!['mass','k','damping','v0'].includes(k):k!=='coefficient'&&(model==='damped'||k!=='damping')).map(k=><label key={k}>{labels[k]}<input required type="number" value={Number.isFinite(args[k])?args[k]:''} step={k==='steps'?1:'any'} onChange={e=>{clear();A({...args,[k]:e.target.valueAsNumber})}}/></label>)}
    <button disabled={busy}>초기값 문제 계산</button>{busy&&<button type="button" onClick={clear}>계산 취소</button>}{err&&<p role="alert">{err}</p>}</form></div>
    {result&&display(result)}{result&&model!=='exponential'&&<button onClick={()=>open(model,{mass:args.mass,k:args.k,x0:args.x0,v0:args.v0,...(model==='damped'?{damping:args.damping}:{})},'미분방정식 · 운동 상태',args.duration)}>같은 초기 조건으로 물리 실험 열기</button>}</>
}
