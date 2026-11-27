import {useState, type PointerEvent} from 'react'
import type {Snapshot} from './domain'
import {numberText} from './domain'
import {MathPlot} from './MathPlot'
import {trigPoint,trigCurve,trigValue,vectors,type TrigSettings,type Triple} from './mathLabModel'

export type OpenPhysics=(model:string,values:Record<string,number>,title:string,duration?:number)=>void
const fmt=(n:number)=>numberText(n,5)
const vec=(v:number[]|null,dim:number)=>v?'('+v.slice(0,dim).map(fmt).join(', ')+')':'정의되지 않음'
function AxisGrid({scale}:{scale:number}){
  const limit=Math.floor(100/scale)
  return <g stroke="#37494e">{Array.from({length:2*limit+1},(_,i)=><path key={i} d={'M'+(120+(i-limit)*scale)+' 20V220 M20 '+(120+(i-limit)*scale)+'H220'}/>)}
  <path d="M20 120H225 M120 220V15" stroke="#b7c8ca"/><g fill="#c4d4d7" stroke="none" fontSize="8"><text x="226" y="124">x</text><text x="126" y="16">y</text><text x={120+5*scale} y="131">5</text><text x="124" y={120-5*scale}>5</text></g></g>
}
export function VectorLab({open}:{open:OpenPhysics}){
  const [dim,D]=useState(2),[u,U]=useState<Triple>([3,0,0]),[v,V]=useState<Triple>([1,0,0]),[k,K]=useState(2)
  const [drag,setDrag]=useState<'u'|'v'|null>(null)
  const actual=(t:Triple):Triple=>[t[0],t[1],dim===3?t[2]:0]
  const left=actual(u),right=actual(v),r=vectors(left,right,k)
  const scale=dim===3?6:10
  const point=(p:number[])=>[120+scale*(p[0]+(dim===3?.45*(p[2]??0):0)),120-scale*(p[1]+(dim===3?.35*(p[2]??0):0))]
  function move(e:PointerEvent<SVGSVGElement>){
    if(!drag || dim!==2)return
    const svg=e.currentTarget,ctm=svg.getScreenCTM()
    if(!ctm)return
    const pos=new DOMPoint(e.clientX,e.clientY).matrixTransform(ctm.inverse())
    const bound=(n:number)=>Math.max(-5,Math.min(5,Math.round(n*10)/10))
    const change=drag==='u'?U:V
    change(prev=>[bound((pos.x-120)/scale),bound((120-pos.y)/scale),prev[2]])
  }
  const arrow=(p:number[],label:string,color:string,id?:'u'|'v')=>{
    const [x,y]=point(p)
    return <g key={label}><path d={'M120 120L'+x+' '+y} stroke={color} strokeWidth="2" markerEnd={'url(#arrow-'+label+')'}/>
    <defs><marker id={'arrow-'+label} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L10 5L0 10z" fill={color}/></marker></defs>
    <text x={x+4} y={y-6} fill={color} fontSize="10">{label}</text>{id&&dim===2&&<circle data-vector={id} cx={x} cy={y} r="7" fill={color} fillOpacity=".55" onPointerDown={e=>{e.currentTarget.ownerSVGElement?.setPointerCapture(e.pointerId);setDrag(id)}}/>}</g>
  }
  const rows=[['합 u+v',vec(r.add,dim)],['차 u−v',vec(r.sub,dim)],['스칼라 배 ku',vec(r.scaled,dim)],['크기 |u|, |v|',fmt(r.len)+', '+fmt(r.otherLen)],
    ['단위 벡터 û',vec(r.unit,dim)],['내적 u·v',fmt(r.dot)],['외적 u×v (3차원)',vec(r.cross,3)],['두 벡터 사이 각',r.angle===null?'정의되지 않음':fmt(r.angle*180/Math.PI)+'°'],
    ['u의 v 방향 정사영',vec(r.projection,dim)],['u의 v에 수직인 성분',vec(r.projection?.map((n,i)=>left[i]-n)??null,dim)],['직교 / 방향 평행',(r.orthogonal?'직교':'직교 아님')+' / '+(r.parallel===null?'방향 없음':r.parallel?'평행':'평행 아님')]]
  const horizontal=dim===2 && u[1]===0 && v[1]===0
  return <><div className="ml-work"><div className="ml-chart"><h3>{dim===2?'평면 벡터':'공간 벡터의 평행 투영'}</h3>
    <svg className="ml-geometry" viewBox="0 0 240 240" role="img" aria-label="벡터 좌표계" onPointerMove={move} onPointerUp={()=>setDrag(null)} onPointerCancel={()=>setDrag(null)}>
      <AxisGrid scale={scale}/>{dim===3&&<path d="M87 146L153 94" stroke="#a5a5ba" strokeDasharray="4 3"/>}
      {[arrow(r.add,'u+v','#f3b78c'),arrow(left,'u','#b8e67b','u'),arrow(right,'v','#7ccfe6','v')]}</svg>
    <p>{dim===2?'u와 v의 끝점을 끌거나 성분을 입력하세요.':'z축을 비스듬히 투영합니다. 길이와 각도는 오른쪽 성분으로 계산합니다.'}</p></div>
    <div className="ml-controls"><label>차원<select value={dim} onChange={e=>D(+e.target.value)}><option value={2}>2차원</option><option value={3}>3차원</option></select></label>
      {([['u',u,U],['v',v,V]] as const).map(([name,t,set])=><fieldset key={name}><legend>벡터 {name} 성분</legend>{['x','y','z'].slice(0,dim).map((axis,i)=><label key={axis}>{name}{axis}<input type="number" step=".1" min="-5" max="5" value={t[i]} onChange={e=>{if(e.target.value && e.target.validity.valid){const val=Number(e.target.value);set(prev=>prev.map((a,j)=>i===j?val:a) as Triple)}}}/></label>)}</fieldset>)}
      <label>스칼라 k<input type="range" min="-5" max="5" step=".1" value={k} onChange={e=>K(+e.target.value)}/>{k}</label></div></div>
    <dl className="ml-results">{rows.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    <div className="ml-bridge"><h3>수평 힘과 일</h3><p>합력 실험은 두 벡터를 N으로 읽습니다. 일 실험은 u를 힘(N), v를 1초 동안의 변위(m)로 읽어 질량 1 kg에 맞는 초기 속도를 설정합니다. 두 실험 모두 수평 벡터가 필요합니다.</p>
      <button disabled={!horizontal} onClick={()=>open('newton',{mass:1,force:r.add[0]},'벡터 합성 · 수평 합력')}>합력을 물리 실험으로</button>
      <button disabled={!horizontal} onClick={()=>open('newton',{mass:1,force:u[0],x0:0,v0:v[0]-u[0]/2},'내적 · 1초 동안의 일',1)}>내적을 일 실험으로</button></div></>
}

export function TrigLab({initial,open,snapshot}:{initial?:TrigSettings;open:OpenPhysics;snapshot:Snapshot|null}){
  const [s,set]=useState<TrigSettings>(initial??{amplitude:1,omega:2,phase:0,t:0,fn:'cos'}),[unit,setUnit]=useState('rad')
  const angle=s.omega*s.t+s.phase, cosine=Math.cos(angle), sine=Math.sin(angle), y=trigPoint(s), deg=unit==='°'
  const factor=deg?180/Math.PI:1, period=s.omega?(s.fn==='tan'?Math.PI:2*Math.PI)/Math.abs(s.omega):null
  const periodWindow=Math.min(20,period??Math.PI*2), extent:[number,number]=[0,Math.max(s.t,periodWindow)]
  const curves=[trigCurve(s,...extent)], mass=snapshot?.experiment.model==='spring'?snapshot.experiment.values.mass:1
  const x0=trigPoint(s,0)??0, v0=s.amplitude*s.omega*(s.fn==='cos'?-Math.sin(s.phase):Math.cos(s.phase)), k=mass*s.omega**2
  const springFits=s.fn!=='tan'&&k>=.5&&k<=100&&Math.abs(x0)<=3&&Math.abs(v0)<=5
  const f=Math.abs(s.omega)/(2*Math.PI),waveFits=s.fn==='sin' && s.omega<0 && Math.abs(s.phase)<1e-12 && s.amplitude>=.001&&s.amplitude<=.04&&f>=.1&&f<=3
  function input(key:'amplitude'|'omega'|'phase'|'t',label:string,min:number,max:number,step:number){
    const mul=key==='phase'?factor:1
    return <label key={key}>{label}<input aria-label={label} type="number" step="any" min={min*mul} max={max*mul} value={Number((s[key]*mul).toPrecision(12))} onChange={e=>{if(e.target.value&&e.target.validity.valid)set({...s,[key]:Number(e.target.value)/mul})}}/>
    <input aria-label={label+' 조절'} type="range" min={min} max={max} step={step} value={s[key]} onChange={e=>set({...s,[key]:+e.target.value})}/></label>
  }
  const tan=trigValue(angle,'tan')
  return <><div className="ml-work"><div><figure className="ml-chart"><figcaption>단위원의 현재 위상</figcaption><svg className="ml-circle" viewBox="0 0 240 172" aria-label="단위원" role="img">
    <path d="M40 86H200 M120 9V163" stroke="#64777f"/><circle cx="120" cy="86" r="62" stroke="#80bdcd" fill="none"/>
    <path d={'M120 86L'+(120+62*cosine)+' '+(86-62*sine)+'V86'} fill="none" stroke="#b6df7f"/><circle cx={120+62*cosine} cy={86-62*sine} r="5" fill="#ffdd87"/>
    </svg><p>θ = {fmt(angle*factor)} {unit} · cos θ = {fmt(cosine)} · sin θ = {fmt(sine)}</p></figure>
    <MathPlot title={'삼각함수 · '+s.fn+' / 가로축 t (s)'} curves={curves} window={extent} marker={y===null?undefined:[s.t,y]}/></div>
    <div className="ml-controls"><label>삼각함수<select value={s.fn} onChange={e=>set({...s,fn:e.target.value as TrigSettings['fn']})}>{['sin','cos','tan'].map(fn=><option key={fn}>{fn}</option>)}</select></label>
    <label>각도 단위<select value={unit} onChange={e=>setUnit(e.target.value)}><option>rad</option><option>°</option></select></label>
    {input('amplitude','배율 A',0,10,.01)}{input('omega','각진동수 ω (rad/s)',-20,20,.01)}{input('phase','위상 φ ('+unit+')',-Math.PI,Math.PI,.01)}{input('t','시각 t (s)',0,20,.01)}
    <p>함숫값 {y===null?'정의되지 않음':fmt(y)} · tan θ = {tan===null?'정의되지 않음':fmt(tan)}</p><p>기본 주기 {s.amplitude===0||period===null?'상수인 구간에서는 정할 수 없음':fmt(period)+' s'}.</p>
    <p>sin² θ + cos² θ = {fmt(sine*sine+cosine*cosine)}. 사인·탄젠트는 홀함수, 코사인은 짝함수입니다.</p></div></div>
    <div className="ml-bridge"><h3>진동과 파동</h3><p>용수철에는 현재 초기 변위·속도와 k=mω²를 전달합니다. 횡파는 원점에서 A sin(−2πft)인 모델입니다.</p>
    <button disabled={!springFits} onClick={()=>open('spring',{mass,k,x0,v0},'삼각함수 · 용수철 운동')}>용수철 운동 열기</button>
    <button onClick={()=>set({amplitude:.03,omega:-2*Math.PI,phase:0,t:0,fn:'sin'})}>횡파 조건 적용</button>
    <button disabled={!waveFits} onClick={()=>open('wave_transverse',{amplitude:s.amplitude,frequency:f},'삼각함수 · 진행 횡파')}>횡파 실험 열기</button></div></>
}
