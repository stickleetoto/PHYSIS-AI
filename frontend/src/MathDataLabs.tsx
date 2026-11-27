import {useEffect,useRef,useState} from 'react'
import {range,numberText,type Snapshot} from './domain'
import {MathPlot} from './MathPlot'
import {parseData,statistics} from './mathStatistics'
import type {LabResult,Point,Curve} from './mathLabModel'

const show=(x:number|null)=>x===null?'정의되지 않음':numberText(x,6)
export function StatsLab({snapshot}:{snapshot:Snapshot|null}){
  const [text,setText]=useState('x,y\n0,1\n1,2\n2,4\n3,5')
  const [data,setData]=useState(()=>parseData(text)),[error,setError]=useState(''),[stale,S]=useState(false)
  const edit=useRef(0)
  const keys=Object.keys(snapshot?.run.series??{}),[chosen,K]=useState('')
  const key=keys.includes(chosen)?chosen:(keys[0]??'')
  const r=statistics(data),extent=range(data.map(p=>p[0]))
  const plots:Curve[]=[{label:'관측쌍 (x,y)',segments:data.map(p=>[p])}]
  if(r.slope!==null)plots.push({label:'최소제곱 회귀선',segments:[extent.map(x=>[x,r.mean+r.slope!*(x-r.mx)] as Point)]})
  function apply(s:string){setText(s);try{setData(parseData(s));setError('');S(false)}catch(e){setError(String((e as Error).message));S(true)}}
  return <><div className="ml-work"><div>{!stale&&<><MathPlot title="관측값과 선형회귀" curves={plots} window={extent}/>
    {r.residuals.length>0&&<MathPlot title="잔차 · 관측값 − 예측값" curves={[{label:'잔차',segments:r.residuals.map(p=>[p])}]} window={extent}/>}
    <figure className="ml-chart"><figcaption>y 히스토그램 · 구간별 빈도</figcaption><svg role="img" aria-label="히스토그램" viewBox="0 0 420 135">{r.hist.map((bin,i)=>{
      const h=90*bin.n/Math.max(...r.hist.map(b=>b.n)),w=390/r.hist.length
      return <g key={i}><title>{show(bin.lo)} ~ {show(bin.hi)} · {bin.n}개</title><rect x={15+i*w} y={106-h} height={h} width={w-1} fill="#8ccbd5"/><text x={15+i*w+w/2} y={103-h} textAnchor="middle" fill="#dce7e8" fontSize="10">{bin.n}</text></g>})}
      <text x="15" y="126" fill="#c7d6db">{show(r.hist[0].lo)}</text><text x="405" y="126" textAnchor="end" fill="#c7d6db">{show(r.hist.at(-1)!.hi)}</text></svg></figure></>}</div>
    <div className="ml-controls"><label>관측쌍 x,y<textarea rows={7} value={text} onChange={e=>{edit.current++;setText(e.target.value);S(true)}}/></label><button onClick={()=>{edit.current++;apply(text)}}>통계 계산</button>
    <label>두 열 CSV 가져오기<input type="file" accept=".csv,text/csv" onChange={async e=>{
      const file=e.target.files?.[0];if(!file)return
      const revision=++edit.current;S(true);setError('')
      try{
        if(file.size>512000)throw new Error('CSV 파일은 500 KiB 이하여야 합니다.')
        const contents=await file.text();if(revision===edit.current)apply(contents)
      }catch(err){if(revision===edit.current)setError(String(err))}
    }}/></label>
    {snapshot&&<><label>현재 물리 실험 측정열<select value={key} onChange={e=>K(e.target.value)}>{keys.map(k=><option key={k}>{k}</option>)}</select></label><button disabled={!key} onClick={()=>{edit.current++;apply(snapshot.run.times.map((t,i)=>t+','+snapshot.run.series[key][i]).join('\n'))}}>시간·측정값 가져오기</button></>}
    {error&&<p role="alert">{error}</p>}{stale&&<p>입력값을 확인하고 통계 계산을 누르세요.</p>}</div></div>
    {!stale&&<dl className="ml-results">{[['관측쌍',r.n],['y 평균',r.mean],['중앙값',r.median],['최빈값',r.modes.length?r.modes.map(show).join(', '):'반복값 없음'],
    ['모분산',r.variance],['모표준편차',Math.sqrt(r.variance)],['표본분산',r.sample],['표본표준편차',r.sample===null?null:Math.sqrt(r.sample)],['상관계수',r.correlation],['회귀 기울기',r.slope],['절편',r.intercept],['결정계수 R²',r.r2]].map(([k,v])=><div key={k}><dt>{k}</dt><dd>{typeof v==='string'?v:show(v as number|null)}</dd></div>)}</dl>}</>
}
export function MatrixLab({display}:{display:(r:LabResult)=>React.ReactNode}){
  const [a,A]=useState('1,1\n0,1'),[b,B]=useState('1,0\n0,1'),[rhs,R]=useState('3,1')
  const [result,O]=useState<LabResult|null>(null),[error,E]=useState(''),[busy,Q]=useState(false)
  const ctl=useRef<AbortController|null>(null)
  useEffect(()=>()=>{ctl.current?.abort()},[])
  function clear(){ctl.current?.abort();ctl.current=null;Q(false);O(null);E('')}
  function parse(s:string){
    return s.trim().split(/\r?\n/).map(line=>line.split(',').map(cell=>{
      if(!cell.trim()||!Number.isFinite(Number(cell)))throw new Error('행과 성분을 확인하세요.')
      return Number(cell)
    }))
  }
  async function calculate(){
    clear();const c=new AbortController();ctl.current=c;Q(true)
    try{
      const right=parse(rhs);if(right.length!==1)throw new Error('우변은 한 줄로 입력하세요.')
      const resp=await fetch('/api/math-lab/matrix',{method:'POST',signal:c.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({a:parse(a),b:parse(b),rhs:right[0]})})
      const body=await resp.json()
      if(!resp.ok||body.status!=='ok')throw new Error(body.detail??'계산을 마치지 못했습니다.')
      if(ctl.current===c)O(body)
    }catch(e){if(ctl.current===c)E((e as Error).message)}finally{if(ctl.current===c)Q(false)}
  }
  const curves=result?.curves??[],extent=range(curves.flatMap(c=>c.segments.flat().map(p=>p[0])),true)
  return <><div className="ml-work"><div>{curves.length>0?<MathPlot title="평면 선형변환 · 원래 격자와 변환 격자" window={extent} curves={curves}/>:<div className="ml-placeholder">2×2 행렬 A로 계산하면 변환 격자와 기저가 나타납니다.</div>}</div>
    <div className="ml-controls">{([['행렬 A',a,A],['행렬 B',b,B],['우변 b',rhs,R]] as const).map(([label,value,set])=><label key={label}>{label}<textarea rows={label==='우변 b'?1:3} value={value} onChange={e=>{clear();set(e.target.value)}}/></label>)}
    <p>행은 줄바꿈, 열은 쉼표로 구분합니다. 각 행렬은 최대 5×5입니다.</p><button onClick={calculate} disabled={busy}>행렬 계산</button>{busy&&<button onClick={clear}>계산 취소</button>}{error&&<p role="alert">{error}</p>}</div></div>
    {result&&<>{display(result)}<section className="ml-panel"><h3>가우스·조르당 소거 과정</h3><ol>{result.steps?.map((s,i)=><li key={i}>{s}</li>)}</ol></section></>}</>
}
