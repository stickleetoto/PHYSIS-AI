import { useEffect, useState } from 'react'
import { ArrowRight, BookOpen, CheckCircle2, FlaskConical, Route } from 'lucide-react'
import { api } from './domain'
import { recordCheckpoint, useLearning } from './learning'

interface Topic {id:string; title:string; stage:number; prerequisites:string[]; models:string[]; misconception:string; checkpoint:{question:string;options:string[]}|null}
interface Graph {nodes:Topic[]; levels:{id:number;title:string}[]; edges:{source:string;target:string;type:string}[]}
interface Resources {readings:{id:string;title:string;locator:string;url:string}[]; models:string[]}
export default function Roadmap({initialTopic,onModel,onMath}:{initialTopic?:string;onModel:(k:string)=>void;onMath:()=>void}) {
  const [graph,setGraph]=useState<Graph|null>(null),[topic,setTopic]=useState(initialTopic??'')
  const [resources,setResources]=useState<Resources|null>(null),[message,setMessage]=useState(''),[error,setError]=useState('')
  const learning=useLearning()
  const history=new Map((learning.checkpoints??[]).map(v=>[v.topic,v]))
  const current=graph?.nodes.find(n=>n.id===topic)
  const review=graph?.nodes.filter(n=>history.get(n.id)?.correct===false)??[]
  const preferredStage={intro:0,school:1,university:2,research:5}[learning.current?.level??'school']
  const eligible=graph?.nodes.filter(n=>n.checkpoint&&!history.get(n.id)?.correct)??[]
  const target=review[0]??eligible.find(n=>n.stage===preferredStage)??eligible[0]
  const recommendation=graph?.nodes.find(n=>target?.prerequisites.includes(n.id)&&n.checkpoint&&!history.get(n.id)?.correct)??target
  useEffect(()=>{api<Graph>('/curriculum').then(setGraph).catch(e=>setError(e.message))},[])
  useEffect(()=>{
    if(graph&&!graph.nodes.some(n=>n.id===topic)) {
      const legacy:Record<string,string>={dimensions:'units',functions:'graphs'}
      setTopic(legacy[topic]??recommendation?.id??'units')
    }
  },[graph,topic,recommendation?.id])
  useEffect(()=>{
    if(!current)return
    let active=true
    setResources(null);setMessage('');setError('')
    api<Resources>('/curriculum/'+current.id+'/resources').then(r=>{if(active)setResources(r)}).catch(e=>{if(active)setError(e.message)})
    return ()=>{active=false}
  },[current?.id])
  async function answer(choice:number) {
    if(!current)return
    try {
      const r=await api<{correct:boolean;reason:string}>('/curriculum/'+current.id+'/answer','POST',{choice})
      recordCheckpoint(current.id,choice,r.correct);setMessage((r.correct?'정답입니다. ':'다시 살펴보세요. ')+r.reason)
    }catch(e){setError(e instanceof Error?e.message:'채점 오류')}
  }
  if(!graph||!current)return <p role="status">{error||'학습 경로를 불러오는 중입니다.'}</p>
  const open=(id:string)=>{setTopic(id);setMessage('')}
  return <section className="roadmap-panel" aria-label="학습 로드맵">
    <section className="roadmap-banner"><div><Route size={21}/><h2>학습 로드맵</h2></div>
      <p>확인 문제 통과 {Array.from(history.values()).filter(v=>v.correct).length} / {graph.nodes.filter(n=>n.checkpoint).length} · 복습 {review.length}</p>
      {recommendation&&<button onClick={()=>open(recommendation.id)}>다음 추천 · {recommendation.title} <ArrowRight size={14}/></button>}</section>
    <div className="roadmap-columns"><nav aria-label="학습 단계">{graph.levels.map(l=><details key={l.id} open={l.id===current.stage}>
      <summary>Level {l.id} · {l.title}</summary>{graph.nodes.filter(n=>n.stage===l.id).map(n=><button key={n.id} aria-pressed={topic===n.id} onClick={()=>open(n.id)}>{n.title}{history.get(n.id)?.correct&&<CheckCircle2 size={15}/>}</button>)}</details>)}</nav>
    <article className="roadmap-detail"><small>Level {current.stage} · {graph.levels[current.stage].title}</small><h2>{current.title}</h2>
      <p>{current.misconception}</p>
      {current.prerequisites.length>0&&<section><h3>선행 개념</h3><div className="study-chips">{current.prerequisites.map(p=><button key={p} onClick={()=>open(p)}>{graph.nodes.find(n=>n.id===p)?.title}</button>)}</div></section>}
      <section><h3><BookOpen size={16}/> 학습 자료</h3>{resources?resources.readings.length>0?resources.readings.map(r=><a href={r.url} target="_blank" rel="noreferrer" key={r.id}>{r.title} · {r.locator} ↗</a>):<p>검토된 읽기 자료 준비 중</p>:<p>자료 조회 중…</p>}</section>
      <section><h3><FlaskConical size={16}/> 연결 도구</h3><div className="study-chips">{current.models.map(m=><button onClick={()=>onModel(m)} key={m}>실험 열기 · {m}</button>)}
      {current.stage===0&&<button onClick={onMath}>기초 수학 도구 열기</button>}</div></section>
      {current.checkpoint?<section><h3>이해도 확인</h3><p>{current.checkpoint.question}</p><div className="roadmap-answers">{current.checkpoint.options.map((v,i)=><button key={v} onClick={()=>void answer(i)}>{v}</button>)}</div>
      {message&&<p role="status">{message}</p>}</section>:<p>이 단원의 개별 확인 문제는 준비 중입니다.</p>}
      {error&&<p role="alert">{error}</p>}</article></div></section>
}
