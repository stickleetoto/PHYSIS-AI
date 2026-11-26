import { useSyncExternalStore } from 'react'
import { api, type Level, type Method, type Snapshot, type Status } from './domain'

export type TutorMode = 'explain' | 'experiment' | 'discovery' | 'equation' | 'review'
export type VisualAction =
  | { op: 'highlight_object' | 'show_force' | 'show_velocity' | 'show_acceleration'; index: number }
  | { op: 'highlight_quantity'; quantity: string }
  | { op: 'highlight_graph'; quantity: string; start: number; end: number }
  | { op: 'seek'; time: number }
  | { op: 'pause' }
  | { op: 'highlight_variable'; variable: string }
  | { op: 'change_conditions' | 'create_comparison'; patch: {values?:Record<string,number>; method?:Method; dt?:number; duration?:number} }
export interface Lesson {
  mode: TutorMode
  title: string
  text: string
  prompt: string
  actions: VisualAction[]
  review?: {question:string; options:string[]; correct:number; feedback:string}
  source?: 'local_journal'
  evidence?: import('./evidence').Evidence
}
export const modeNames: Record<TutorMode, string> = {
  explain:'개념 설명', experiment:'실험 설계', discovery:'발견 학습', equation:'공식 탐구', review:'개념 복습',
}
interface Entry {
  id: string
  time: string
  experimentId: string | null
  revision: number | null
  topic: string
  title: string
  level: Level
}
interface ExperimentEntry extends Entry {
  kind:'experiment'
  values:Record<string,number>
  method:Method
  dt:number
  duration:number
  status:Status
  facts:Record<string,number>
}
interface Turn extends Entry {
  kind:'turn'
  message:string
  reply:string
  lesson:Lesson|null
}
interface Evidence extends Entry {
  kind:'hypothesis'|'observation'|'conclusion'|'note'|'bookmark'|'self'|'answer'
  text:string
  parent?:string
  verdict?:'understood'|'review'
  chosen?:string
  feedback?:string
}
export type LearningEvent = ExperimentEntry | Turn | Evidence
export interface LearningState {
  version:2
  current: { experimentId:string|null; topic:string; level:Level } | null
  events: LearningEvent[]
  checkpoints?: {topic:string; choice:number; correct:boolean; time:string}[]
}
const key = 'physis.learning.v2'
const empty = ():LearningState => ({version:2,current:null,events:[]})
function read(): LearningState {
  try {
    const data = JSON.parse(localStorage.getItem(key) ?? 'null')
    if (data?.version === 2 && Array.isArray(data.events)) return data as LearningState
  } catch { /* A browser can disable local storage. */ }
  return empty()
}
let state = read()
let storageWarning = ''
const listeners = new Set<()=>void>()
function publish(next:LearningState) {
  state = next
  try {
    localStorage.setItem(key, JSON.stringify(state))
    storageWarning = ''
  } catch {
    storageWarning = '브라우저 저장소에 쓸 수 없습니다. 창을 닫기 전에 기록을 내보내세요.'
  }
  listeners.forEach(fn=>fn())
}
if (typeof window !== 'undefined') window.addEventListener('storage', event=>{
  if (event.key === key || event.key === null) {
    state = read()
    listeners.forEach(fn=>fn())
  }
})
const subscribe = (fn:()=>void) => {listeners.add(fn); return ()=>{listeners.delete(fn)}}
export const useLearning = () => useSyncExternalStore(subscribe, ()=>state)
export const getLearning = () => state
export function recordCheckpoint(topic:string,choice:number,correct:boolean) {
  publish({...state,checkpoints:[...(state.checkpoints??[]),{topic,choice,correct,time:new Date().toISOString()}]})
}
export const learningWarning = () => storageWarning
function entry(s:Snapshot|null, level:Level):Entry {
  return {id:crypto.randomUUID(),time:new Date().toISOString(),experimentId:s?.experiment.id??null,
    revision:s?.revision??null,topic:s?.experiment.model??'',title:s?.experiment.title??'일반 질문',level}
}
function context(s:Snapshot, level:Level) {
  return {experimentId:s.experiment.id, topic:s.experiment.model,level}
}
export function recordExperiment(s:Snapshot, level:Level) {
  const existing = state.events.some(e=>e.kind==='experiment' && e.experimentId===s.experiment.id && e.revision===s.revision)
  const item:ExperimentEntry = {...entry(s,level),kind:'experiment',values:s.experiment.values,method:s.experiment.method,
    duration:s.experiment.duration,dt:s.experiment.dt,status:s.run.status,facts:s.run.facts}
  publish({...state,current:context(s,level),events:existing?state.events:[...state.events,item]})
}
export function recordTurn(message:string, lesson:Lesson|null, s:Snapshot|null, level:Level, reply='') {
  if (s) recordExperiment(s,level)
  const item:Turn={...entry(s,level),kind:'turn',message,lesson,reply:lesson?.text ?? reply}
  publish({...state,events:[...state.events,item]})
}

/** Resolve explicit personal recall from this experiment before any provider request. */
export function recallLearning(message:string,s:Snapshot,mode:TutorMode):Lesson|null {
  if (!/(내가|내\s|나의|아까|이전|지난|최근|직전|전에|저번|기록한|적어\s*둔|적었던|세웠던)/.test(message)
      || !/(뭐|무엇|어떤|알려|보여|찾|기억|꺼내|읽어|다시\s*보|확인해|돌아보|정리해)/.test(message)) return null
  const kinds = [
    ['hypothesis','가설',/가설|예측/],['observation','관찰',/관찰/],['conclusion','결론',/결론/],
    ['note','메모',/메모|노트/],['turn','질문',/질문/],
  ] as const
  const requested=kinds.filter(([, ,pattern])=>pattern.test(message))
  if (!requested.length) return null
  const entries=state.events.filter(e=>e.experimentId===s.experiment.id)
  const paragraphs=requested.map(([kind,name])=>{
    const recent=entries.filter(e=>e.kind===kind && (e.kind!=='turn'||e.lesson?.source!=='local_journal')).slice(-3).reverse()
    if (!recent.length) return `이 실험에 직접 기록한 ${name}이 아직 없습니다.`
    return recent.map(e=>{
      const date=new Date(e.time).toLocaleString('ko-KR',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})
      const words=e.kind==='turn'?e.message:'text' in e?e.text:''
      return `${name} · v${e.revision} · ${date}\n“${words}”`
    }).join('\n\n')
  })
  return {mode,source:'local_journal',title:'내 학습 기록에서 찾은 내용',text:paragraphs.join('\n\n'),
    prompt:'현재 실험에 직접 입력한 기록을 최근순으로 표시합니다.',actions:[]}
}
export function addEvidence(s:Snapshot,level:Level, kind:Evidence['kind'], text:string,
  detail:Pick<Evidence,'parent'|'verdict'|'chosen'|'feedback'>={}) {
  if (!text.trim()) return
  recordExperiment(s,level)
  const item:Evidence={...entry(s,level),kind,text:text.trim(),...detail}
  publish({...state,events:[...state.events,item]})
}
export function clearLearning() {
  localStorage.removeItem(key)
  state=empty()
  storageWarning=''
  listeners.forEach(fn=>fn())
}
export async function learningArchive() {
  const server = await api<{experiments:unknown[];workbenches:unknown[];usage:unknown[]}>('/learning/export')
  if (![server.experiments,server.workbenches,server.usage].every(Array.isArray)) {
    throw new Error('서버 학습 기록의 형식을 확인할 수 없습니다.')
  }
  return {...state,scope:'이 브라우저의 학습 기록·대화와 로컬 서버에 저장된 실험·비교 구성·사용 기록',
    server:{experiments:server.experiments,workbenches:server.workbenches,usage:server.usage},
    legacy:{history:JSON.parse(localStorage.getItem('physis-history')??'[]'),messages:JSON.parse(localStorage.getItem('physis-messages')??'{}')}}
}
export async function exportLearning() {
  const archive=await learningArchive()
  const blob = new Blob([JSON.stringify(archive,null,2)],{type:'application/json;charset=utf-8'})
  const url=URL.createObjectURL(blob)
  const link=document.createElement('a')
  link.href=url
  link.download='PHYSIS-학습기록.json'
  link.click()
  window.setTimeout(()=>URL.revokeObjectURL(url),1000)
}
export function latestJudgments(events:LearningEvent[]) {
  const latest=new Map<string,Evidence>()
  for (const e of events) {
    if ((e.kind==='self'||e.kind==='answer') && e.verdict) latest.set(e.topic,e)
  }
  return latest
}
