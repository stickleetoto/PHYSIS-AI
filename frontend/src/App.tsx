import { lazy, Suspense, useCallback, useEffect, useEffectEvent, useRef, useState, type FormEvent } from 'react'
import {
  Activity,
  ArrowDownToLine,
  ArrowUp,
  Atom,
  Boxes,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  FlaskConical,
  History,
  LayoutGrid,
  Lightbulb,
  LoaderCircle,
  MessageSquareText,
  Microscope,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  StepForward,
  X,
  GraduationCap, Sigma, LibraryBig, Settings2, ChartSpline,
} from 'lucide-react'
import {
  api,
  colors,
  defaultQuantity,
  exportCsv,
  methods,
  numberText,
  quantities,
  sampleIndex,
  statuses,
  type ChatResult,
  type Classification,
  type DialogueState,
  type Level,
  type ModelSpec,
  type Patch,
  type Snapshot,
} from './domain'
import { GraphPanel } from './GraphPanel'
import { Inspector } from './Inspector'
import { Scene } from './Scene'
import { CompareBench } from './CompareBench'
import { displayedComparison, readTutorStream, type Board, type Selection, type FocusAction, type ComparisonSelection } from './bench'
import { ExperimentControls, saveExperimentFile, ToolsDialog } from './ExperimentControls'
import { LabLearningTools } from './LabLearningTools'
import { ProviderSettings } from './ProviderSettings'
import { TutorPanel } from './TutorPanel'
import { LearningView } from './LearningView'
import { recordExperiment, recordTurn, clearLearning, getLearning } from './learning'
import { FieldScene, isFieldModel } from './FieldScene'
import './studio.css'
import './research.css'
import { ResearchView, type StudyTarget } from './ResearchView'
import { fromPhysics, type MathEntry } from './mathLabModel'
const MathematicsLab = lazy(() => import('./MathematicsLab').then(m=>({default:m.MathematicsLab})))

type View = 'lab'|'tutor'|'formula'|'numerical'|'learning'|'research'|'mathematics'
const ScienceView = lazy(() => import('./ScienceView').then(module => ({default: module.ScienceView})))
type PanelProps = Parameters<typeof TutorPanel>[0]
type Mode = PanelProps['mode']
type Lesson = NonNullable<PanelProps['lesson']>

type HistoryEntry = { id: string; title: string; model: string }
type ChatEntry = { role: 'user' | 'assistant'; text: string; unsupported?: boolean; classification?: Classification; assumptions?: string[] }
type Messages = Record<string, ChatEntry[]>
type Dialogues = Record<string, DialogueState>
type Drawer = 'catalog' | 'history' | null
function readHistory(): HistoryEntry[] {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem('physis-history') ?? '[]')
    return Array.isArray(raw)
      ? raw
          .filter(
            (v) =>
              v &&
              typeof v.id === 'string' &&
              typeof v.title === 'string' &&
              typeof v.model === 'string',
          )
          .slice(0, 24)
      : []
  } catch {
    return []
  }
}
function writeHistory(items: HistoryEntry[]) {
  try {
    localStorage.setItem('physis-history', JSON.stringify(items))
  } catch {
    /* Storage may be disabled. */
  }
}
function readMessages(): Messages {
  try {
    const source = JSON.parse(localStorage.getItem('physis-messages') ?? '{}')
    return Object.fromEntries(
      readHistory().map((h) => [
        h.id,
        Array.isArray(source?.[h.id])
          ? source[h.id]
              .filter(
                (v: ChatEntry) =>
                  v && ['user', 'assistant'].includes(v.role) && typeof v.text === 'string',
              )
              .slice(-20)
          : [],
      ]),
    )
  } catch {
    return {}
  }
}
function readDialogues(): Dialogues {
  try {
    const source: unknown = JSON.parse(localStorage.getItem('physis-dialogues') ?? '{}')
    if (!source || typeof source !== 'object' || Array.isArray(source)) return {}
    return Object.fromEntries(
      readHistory().flatMap((entry) => {
        const value = (source as Record<string, unknown>)[entry.id]
        return value && typeof value === 'object' && !Array.isArray(value)
          && typeof (value as DialogueState).id === 'string'
          && typeof (value as DialogueState).original_message === 'string'
          ? [[entry.id, value as DialogueState]]
          : []
      }),
    )
  } catch { return {} }
}
function Brand() {
  return (
    <div className="brand">
      <img src="/physis.svg" alt="" width="32" height="32" />
      <span>PHYSIS</span>
      <b>AI</b>
    </div>
  )
}
export function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null),
    [previous, setPrevious] = useState<Snapshot>()
  const [catalog, setCatalog] = useState<ModelSpec[]>([]),
    [provider, setProvider] = useState('')
  const [history, setHistory] = useState<HistoryEntry[]>(readHistory),
    [drawer, setDrawer] = useState<Drawer>(null)
  const [mobileChat, setMobileChat] = useState(false),
    [level, setLevel] = useState<Level>(() => getLearning().current?.level ?? 'school')
  const [view,setView]=useState<View>('lab'), [mode,setMode]=useState<Mode>('explain')
  const [study,setStudy]=useState<StudyTarget>({tab:'library'})
  const [mathEntry,setMathEntry]=useState<MathEntry>({topic:'function'})
  const [lesson,setLesson]=useState<Lesson|null>(null), [notice,setNotice]=useState('')
  const [focus,setFocus]=useState<FocusAction[]>([])
  const [settings,setSettings]=useState(false)
  const [selection,setSelection]=useState<Selection|null>(()=>{
    try { const s=JSON.parse(localStorage.getItem('physis-provider')||'null')
      return s&&typeof s.provider==='string'&&typeof s.model==='string'?s:null
    } catch {return null}
  })
  const aborter=useRef<AbortController|null>(null)
  const [board,setBoard]=useState<Board|null>(null),[benchVersion,setBenchVersion]=useState(0)
  const [comparison,setComparison]=useState<ComparisonSelection>({quantity:null,object_index:0})
  const [formReset,setFormReset]=useState(0)
  const [learningTools,setLearningTools]=useState(false)
  const [inputHistory,setInputHistory]=useState<{id:string;revision:number;undo:number;redo:number}|null>(null)
  const importer=useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(true),
    [error, setError] = useState(''),
    lock = useRef(false)
  const [messages, setMessages] = useState<Messages>(readMessages),
    [dialogues, setDialogues] = useState<Dialogues>(readDialogues),
    [draft, setDraft] = useState('')
  const [elapsed, setElapsed] = useState(0),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1)
  const [discover, setDiscover] = useState(false),
    [revealed, setRevealed] = useState(false)
  const [hypothesis, setHypothesis] = useState(''),
    [prediction, setPrediction] = useState(''),
    [notes, setNotes] = useState('')
  const chatEnd = useRef<HTMLDivElement>(null)
  const hidden = discover && !revealed
  const activeBoard = board?.members.some(m=>m.experiment.id===snapshot?.experiment.id) ? board : null
  const end = Math.max(snapshot?.run.times.at(-1) ?? 0,...(activeBoard?.members.map(s=>s.run.times.at(-1)??0)??[]))
  const index = snapshot ? sampleIndex(snapshot.run.times, elapsed) : 0
  function nextFrame() {
    const members = activeBoard?.members ?? (snapshot ? [snapshot] : [])
    const next = members.map(s => s.run.times.find(t => t > elapsed + 1e-10) ?? end)
    seek(Math.min(end, ...next))
  }
  const accept = useCallback((s: Snapshot) => {
    setSnapshot(s)
    setDialogues((all) => {
      const state = all[s.experiment.id]
      if (!state || state.revision === s.revision) return all
      const next = { ...all }
      delete next[s.experiment.id]
      return next
    })
    setLesson(null)
    setFocus([])
    setNotice('')
    setElapsed(0)
    setPlaying(false)
    setHistory((items) => {
      const next = [
        { id: s.experiment.id, title: items.find(h=>h.id===s.experiment.id)?.title ?? s.experiment.title, model: s.experiment.model },
        ...items.filter((h) => h.id !== s.experiment.id),
      ].slice(0, 24)
      writeHistory(next)
      return next
    })
  }, [])
  const perform = useCallback(async (fn: () => Promise<void>) => {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    setError('')
    try {
      await fn()
    } catch (err) {
      setError(err instanceof Error ? err.message : '실험 요청을 처리할 수 없습니다.')
    } finally {
      lock.current = false
      setBusy(false)
    }
  }, [])
  const init = useCallback(
    () =>
      perform(async () => {
        const data = await api<{ models: ModelSpec[]; provider: string }>('/catalog')
        setCatalog(data.models)
        setProvider(data.provider)
        const learning = getLearning().current
        const savedLevel = learning?.level ?? 'school'
        setLevel(savedLevel)
        const last = learning?.experimentId ?? readHistory()[0]?.id
        if (last) {
          try {
            accept(
              await api<Snapshot>('/experiments/' + encodeURIComponent(last) + '?level=' + savedLevel),
            )
            return
          } catch (err) {
            if (!(err instanceof Error && err.message.includes('찾을 수 없'))) throw err
          }
        }
        accept(await api<Snapshot>('/experiments', 'POST', { model: 'free_fall', level: 'school' }))
      }),
    [accept, perform],
  )
  useEffect(() => {
    void init()
  }, [init])
  useEffect(()=>{
    if(!snapshot)return
    let stale=false
    api<Board>('/workbenches/'+snapshot.experiment.id+'?level='+level)
      .then(value=>{if(!stale)setBoard(value)})
      .catch(err=>{if(!stale)setError(err.message)})
    return ()=>{stale=true}
  },[snapshot?.experiment.id,snapshot?.revision,benchVersion,level])
  useEffect(()=>{
    if(!snapshot)return
    const id=snapshot.experiment.id
    let stale=false
    api<{revision:number;undo:number;redo:number}>('/experiments/'+id+'/history')
      .then(value=>{if(!stale)setInputHistory({id,...value})})
      .catch(err=>{if(!stale)setError(err.message)})
    return ()=>{stale=true}
  },[snapshot?.experiment.id,snapshot?.revision])
  useEffect(()=>{
    if(!board?.display_names)return
    const titles=new Map(board.members.map(s=>[s.experiment.id,board.display_names?.[s.experiment.id]||s.experiment.title]))
    setHistory(items=>{
      if(!items.some(h=>titles.has(h.id)&&titles.get(h.id)!==h.title))return items
      const next=items.map(h=>({...h,title:titles.get(h.id)??h.title}))
      writeHistory(next)
      return next
    })
  },[board])
  useEffect(()=>()=>{aborter.current?.abort()},[])
  useEffect(() => {
    if (!playing) return
    let frame: number, last: number | undefined
    const tick = (now: number) => {
      const delta = last === undefined ? 0 : ((now - last) * speed) / 1000
      last = now
      setElapsed((t) => Math.min(t + delta, end))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, speed, end])
  useEffect(() => {
    if (playing && elapsed >= end) setPlaying(false)
  }, [elapsed, end, playing])
  useEffect(() => {
    if (chatEnd.current) {
      const parent = chatEnd.current.parentElement
      if (parent) parent.scrollTop = parent.scrollHeight
    }
  }, [messages])
  useEffect(() => {
    const bounded = Object.fromEntries(
      history.filter((h) => messages[h.id]?.length).map((h) => [h.id, messages[h.id].slice(-20)]),
    )
    try {
      localStorage.setItem('physis-messages', JSON.stringify(bounded))
    } catch {
      /* The current session remains accessible when storage is full. */
    }
  }, [messages, history])
  useEffect(() => {
    const bounded = Object.fromEntries(history.flatMap((entry) => {
      const state = dialogues[entry.id]
      return state ? [[entry.id, state]] : []
    }))
    try { localStorage.setItem('physis-dialogues', JSON.stringify(bounded)) } catch { /* local state remains available for this tab */ }
  }, [dialogues, history])
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === 'physis-dialogues' || event.key === null) setDialogues(readDialogues())
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])
  const resetDiscovery = () => {
    setRevealed(false)
    setHypothesis('')
    setPrediction('')
    setNotes('')
  }
  const openModel = (model: string, preset?:{title:string;initialValues:Record<string,number>;duration?:number}) =>
    perform(async () => {
      const s = await api<Snapshot>('/experiments', 'POST', { model, level,
        ...(preset?{display_name:preset.title,patch:{values:preset.initialValues,duration:preset.duration}}:{}) })
      accept(s)
      recordExperiment(s,level)
      setPrevious(undefined)
      setDrawer(null)
      setLearningTools(false)
      setMobileChat(false)
      resetDiscovery()
    })
  const reopen = (id: string) =>
    perform(async () => {
      const s = await api<Snapshot>('/experiments/' + encodeURIComponent(id) + '?level=' + level)
      accept(s)
      recordExperiment(s,level)
      setPrevious(undefined)
      setDrawer(null)
      resetDiscovery()
    })
  const patch = (patch: Partial<Patch>) =>
    perform(async () => {
      if (!snapshot) return
      const s = await api<Snapshot>('/experiments/' + snapshot.experiment.id, 'PATCH', {
        patch,
        revision: snapshot.revision,
        level,
      })
      setPrevious(snapshot)
      accept(s)
      recordExperiment(s,level)
      if (discover) resetDiscovery()
    })
  const changeLevel = (next: Level) =>
    perform(async () => {
      if (!snapshot) return
      const s = await api<Snapshot>('/experiments/' + snapshot.experiment.id + '?level=' + next)
      setSnapshot(s)
      setLevel(next)
      recordExperiment(s,next)
      setLesson(null)
      setFocus([])
    })
  const append = (id: string, entry: ChatEntry) =>
    setMessages((list) => ({ ...list, [id]: [...(list[id] ?? []), entry] }))
  const rememberDialogue = (id: string, value: DialogueState | null | undefined, used?: DialogueState) =>
    setDialogues((all) => {
      const current = all[id]
      if (used && current?.id === used.id && (current.turn ?? 0) > (used.turn ?? 0)) return all
      const next = { ...all }
      if (value) next[id] = value
      else delete next[id]
      return next
    })
  const send = (input: string) =>
    perform(async () => {
      if (!snapshot || !input.trim() || hidden) return
      const source = snapshot.experiment.id,
        message = input.trim(),
        dialogue = dialogues[source]
      append(source, { role: 'user', text: message })
      setDraft('')
      const data = await api<ChatResult & {lesson?:Lesson}>('/chat', 'POST', {
        message,
        experiment_id: source,
        revision: snapshot.revision,
        level,
        dialogue: dialogue ?? null,
      })
      const answer: ChatEntry = {
        role: 'assistant',
        text: data.message,
        unsupported: data.action === 'unsupported',
        classification: data.classification,
        assumptions: data.assumptions,
      }
      rememberDialogue(source, data.dialogue, dialogue)
      recordTurn(message,data.lesson??null,data.snapshot??snapshot,data.level,data.message)
      if (data.snapshot) {
        const target = data.snapshot.experiment.id
        if (target !== source) {
          setMessages((list) => ({ ...list, [target]: [{ role: 'user', text: message }, answer] }))
          append(source, answer)
        } else append(target, answer)
        if (data.action === 'modify') setPrevious(snapshot)
        if (data.action === 'create') setPrevious(undefined)
        if (data.action === 'explain') setSnapshot(data.snapshot)
        else {
          accept(data.snapshot)
          resetDiscovery()
        }
        setLevel(data.level)
      } else append(source, answer)
    })
  const askTutor=(input:string)=>perform(async()=>{
    if(!snapshot||!input.trim())return
    const message=input.trim(), controller=new AbortController(), dialogue=dialogues[snapshot.experiment.id]
    aborter.current=controller
    setNotice('질문을 읽고 있습니다.')
    let paragraphs=''
    try {
      const prior = [...(messages[snapshot.experiment.id]??[])].reverse().find(entry=>entry.role==='user')
      await readTutorStream({message,experiment_id:snapshot.experiment.id,revision:snapshot.revision,
        previous_question:prior?.text.slice(0,600),
        mode,level,selection,dialogue:dialogue??null},controller.signal,event=>{
        if(event.event==='stage')setNotice(event.stage)
        if(event.event==='text'){paragraphs+=(paragraphs?'\n\n':'')+event.text;setNotice(paragraphs)}
        if(event.event!=='result')return
        const data=event.result, s:Snapshot|null=data.snapshot, next:Lesson|null=data.lesson
        rememberDialogue(snapshot.experiment.id,data.dialogue,dialogue)
        if(s){
          if(data.action==='modify')setPrevious(snapshot)
          if(data.action==='create'||data.action==='compare')setPrevious(undefined)
          if(data.action==='explain')setSnapshot(s)
          else {accept(s);resetDiscovery()}
          setLevel(data.level)
          setLesson(next)
          const actions:FocusAction[]=next?.actions??[]
          setFocus(actions)
          const cursor=actions.find(a=>a.op==='seek')
          if(cursor?.time!==undefined)seek(cursor.time)
          if(actions.some(a=>a.op==='pause'))setPlaying(false)
          if(data.action==='compare')setBenchVersion(v=>v+1)
        }
        if(!s && next){setLesson(next);setFocus([])}
        recordTurn(message,next,s??snapshot,data.level,data.message)
        const id=(s??snapshot).experiment.id
        append(id,{role:'user',text:message})
        append(id,{role:'assistant',text:data.message,unsupported:data.action==='unsupported',
          classification:data.classification,assumptions:data.assumptions})
        setDraft('')
        setNotice(s||next?'':data.message)
      })
    } catch(err){
      // A network interruption can occur just after the server commits a revision.
      try {
        const current = await api<Snapshot>('/experiments/'+snapshot.experiment.id+'?level='+level)
        if(current.revision!==snapshot.revision){accept(current);recordExperiment(current,level)}
      } catch { /* The connection may still be unavailable. */ }
      setBenchVersion(v=>v+1)
      if(controller.signal.aborted){setNotice('요청을 취소했습니다.')}
      else {setNotice('');throw err}
    } finally {aborter.current=null}
  })
  const clone=(model?:string)=>perform(async()=>{
    if(!snapshot)return
    const s=await api<Snapshot>('/workbenches/'+snapshot.experiment.id+'/members','POST',
      {revision:snapshot.revision,level,...(model?{model}:{})})
    accept(s);setPrevious(undefined);recordExperiment(s,level)
  })
  const sendFromLab = (input: string) => selection || provider!=='mock' || /문헌|논문|인용|근거|선행|소각|복제|비교\s*실험|강조|벡터|일시\s*정지|초.*이동|바꿔.*비교/.test(input)
    ? askTutor(input) : send(input)
  const selectMember=(s:Snapshot)=>{
    setSnapshot(s);setPrevious(undefined);setLesson(null);setFocus([]);resetDiscovery();setNotice('')
    recordExperiment(s,level)
  }
  const removeMember=(id:string)=>perform(async()=>{
    if(!snapshot||!activeBoard)return
    await api('/workbenches/'+snapshot.experiment.id+'/members/'+id,'DELETE')
    if(snapshot.experiment.id===id)selectMember(activeBoard.members[0])
    setBenchVersion(v=>v+1)
  })
  const erase=async()=>{
    if(lock.current)throw new Error('계산이 끝난 뒤 삭제하세요.')
    lock.current=true
    setBusy(true)
    try {
      await api('/learning','DELETE')
      clearLearning()
      for(const k of ['physis-history','physis-messages','physis-dialogues'])localStorage.removeItem(k)
      setHistory([]);setMessages({});setDialogues({});setSnapshot(null);setBoard(null);setPrevious(undefined);setFocus([]);setLesson(null)
      setDraft('');setPlaying(false);setDiscover(false);resetDiscovery()
      setLevel('school');setNotice('');setError('')
    } finally {
      lock.current=false
      setBusy(false)
    }
  }
  const toggleDiscovery = () => {
    setDiscover(!discover)
    setPlaying(false)
    setElapsed(0)
    resetDiscovery()
  }
  const seek = (time: number) => {
    setPlaying(false)
    setElapsed(time)
  }
  const experiment = snapshot?.experiment
  const status = snapshot?.run.status
  const changeView=(next:View, seed=true)=>{
    setView(next);setDrawer(null);setMobileChat(false);setPlaying(false)
    if(seed && next!=='learning' && next!=='research' && !snapshot)void init()
  }
  const openStudy=(target:StudyTarget)=>{setStudy(target);changeView('research',false)}
  const displayTitle = experiment && (activeBoard?.display_names?.[experiment.id] || experiment.title)
  const available = inputHistory?.id===experiment?.id && inputHistory?.revision===snapshot?.revision ? inputHistory : null
  const moveHistory=(direction:'undo'|'redo')=>perform(async()=>{
    if(!snapshot || !available?.[direction])return
    const s=await api<Snapshot>('/experiments/'+snapshot.experiment.id+'/history/'+direction,'POST',{revision:snapshot.revision,level})
    setPrevious(snapshot);accept(s);recordExperiment(s,level);resetDiscovery()
  })
  const resetInputs=()=>{
    if(!experiment)return
    const defaults=catalog.find(model=>model.model===experiment.model)
    if(!defaults)return
    const values=Object.fromEntries(defaults.variables.map(v=>[v.key,v.default]))
    seek(0)
    setFormReset(n=>n+1)
    if(defaults.dt!==experiment.dt || defaults.duration!==experiment.duration || defaults.methods[0]!==experiment.method
      || Object.keys(values).some(key=>values[key]!==experiment.values[key])){
      void patch({values,method:defaults.methods[0],dt:defaults.dt,duration:defaults.duration})
    }
  }
  const rename=(name:string)=>perform(async()=>{
    if(!snapshot)return
    const id=snapshot.experiment.id
    const result=await api<{display_name:string|null;name_revision:number}>('/experiments/'+id+'/display-name','PATCH',{
      revision:snapshot.revision,display_name:name,name_revision:activeBoard?.name_revisions?.[id]??0})
    setBoard(current=>current?{...current,display_names:{...current.display_names,[id]:result.display_name},
      name_revisions:{...current.name_revisions,[id]:result.name_revision}}:current)
    setBenchVersion(v=>v+1)
  })
  const saveFile=()=>perform(async()=>{
    if(!snapshot)return
    const members=activeBoard?.members.map(s=>s.experiment.id===snapshot.experiment.id?snapshot:s)??[snapshot]
    const {quantity,object_index}=displayedComparison(members,snapshot,comparison)
    const file=await api('/portable/experiments/export','POST',{experiment_id:snapshot.experiment.id,revision:snapshot.revision,
      view:{quantity,object_index,elapsed,speed}})
    saveExperimentFile(file, displayTitle ?? snapshot.experiment.title)
  })
  const loadFile=(file:File)=>perform(async()=>{
    if(!file.size || file.size>128*1024)throw new Error('저장 파일은 1바이트 이상 128 KiB 이하여야 합니다.')
    const imported=await api<{active_id:string;level:Level;view:ComparisonSelection & {elapsed:number;speed:number}}>(
      '/portable/experiments/import','POST',file)
    const restored=await api<Board>('/workbenches/'+imported.active_id+'?level='+imported.level)
    const current=restored.members.find(s=>s.experiment.id===imported.active_id)
    if(!current)throw new Error('불러온 비교 실험에서 선택한 실험을 찾을 수 없습니다.')
    accept(current);setBoard(restored);setPrevious(undefined);setLevel(imported.level);setDiscover(false);resetDiscovery()
    recordExperiment(current,imported.level);changeView('lab',false)
    setComparison({quantity:imported.view.quantity,object_index:imported.view.object_index})
    setSpeed(imported.view.speed)
    seek(Math.min(imported.view.elapsed,Math.max(...restored.members.map(s=>s.run.times.at(-1)??0))))
  })
  const togglePlay=()=>{if(!playing && elapsed>=end)setElapsed(0);setPlaying(!playing)}
  const handleShortcut=useEffectEvent((event:KeyboardEvent)=>{
    if(event.defaultPrevented || event.isComposing || event.repeat || event.altKey || event.metaKey || event.shiftKey
      || view==='mathematics' || busy || lock.current || drawer || settings || learningTools
      || (event.target instanceof Element && event.target.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],dialog')))return
    const key=event.key.toLowerCase()
    if(event.ctrlKey && key==='o'){event.preventDefault();importer.current?.click();return}
    if(!snapshot)return
    if(event.ctrlKey){
      if(!['s','z','y'].includes(key))return
      event.preventDefault()
      if(key==='s')void saveFile()
      else void moveHistory(key==='z'?'undo':'redo')
    } else if(view==='lab' && key==='r'){event.preventDefault();resetInputs()}
    else if((view==='lab'||view==='tutor') && !hidden && (key===' ' || key==='n')){
      event.preventDefault()
      if(key===' ')togglePlay()
      else nextFrame()
    }
  })
  useEffect(()=>{const listener=(event:KeyboardEvent)=>handleShortcut(event)
    window.addEventListener('keydown',listener);return ()=>window.removeEventListener('keydown',listener)
  },[])
  const focusVariable=focus.find(a=>a.op==='highlight_variable')?.variable
  const scene = snapshot && (isFieldModel(snapshot.experiment.model)
    ? <FieldScene snapshot={snapshot} index={index} focus={focus} displayTitle={displayTitle}/>
    : <Scene key={snapshot.experiment.id} snapshot={snapshot} index={index} focus={focus} displayTitle={displayTitle}/>)
  const tutorScene=snapshot&&<div className="tutor-evidence">
    {scene}
    <div className="tutor-playbar"><button onClick={()=>{if(elapsed>=end)setElapsed(0);setPlaying(!playing)}}>{playing?<Pause size={15}/>:<Play size={15}/>} {playing?'멈추기':'실험 재생'}</button>
      <input type="range" aria-label="튜터 시각" min={0} max={end} step="any" value={elapsed} onChange={e=>seek(+e.target.value)}/>
      <output>{numberText(elapsed)} s</output></div>
    <FocusReadout snapshot={snapshot} index={index} focus={focus}/>
    {focus.some(a=>a.op==='highlight_graph'||a.op==='highlight_quantity')&&<GraphPanel snapshot={snapshot} index={index} onSeek={seek} focus={focus} displayTitle={displayTitle}/>}
  </div>
  return (
    <div className="app">
      <input hidden type="file" accept=".json,application/json" aria-label="실험 JSON 파일" ref={importer}
        onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void loadFile(file)}}/>
      <header className="masthead">
        <Brand />
        <span className="brand-divider" />
        <span className="product-name">물리 탐구실</span>
        <nav className="topnav" aria-label="워크스페이스 탐색">
          {([['tutor','튜터',GraduationCap],['lab','실험실',FlaskConical],['mathematics','수학 실험실',LayoutGrid],['formula','공식',Sigma],['numerical','수치해석',ChartSpline],['research','지식 탐구',Search],['learning','학습 기록',LibraryBig]] as const).map(([key,label,Icon])=>
            <button key={key} disabled={busy} aria-pressed={view===key&&!drawer} onClick={()=>changeView(key)}><Icon size={15}/>{label}</button>)}
        </nav>
        <div className="catalog-tools">
          <button onClick={()=>{setLearningTools(true);setPlaying(false)}}>프리셋·단위 변환</button>
          <button aria-pressed={drawer === 'catalog'} onClick={() => setDrawer('catalog')}>
            <LayoutGrid size={15} />
            실험 목록
          </button>
          <button aria-pressed={drawer === 'history'} onClick={() => setDrawer('history')}>
            <History size={15} />
            기록
          </button>
        </div>
        <button className="provider" aria-label="AI 공급자 설정" onClick={()=>setSettings(true)} disabled={busy}>
          <i className={snapshot && (selection?.provider??provider)==='mock' ? 'connected' : ''} />
          {selection?.provider??provider??'AI'} <Settings2 size={14}/>
        </button>
        {view==='lab'&&<button
          className={'chat-toggle ' + (mobileChat ? 'active' : '')}
          aria-label="어시스턴트 열기"
          onClick={() => setMobileChat(!mobileChat)}
        >
          <MessageSquareText size={17} />
        </button>}
      </header>
      <div className={'layout '+(view==='lab'?'':'study-layout')}>
        <aside
          className={'assistant ' + (mobileChat ? 'mobile-visible' : '')}
          aria-label="실험 어시스턴트"
        >
          <header className="assistant-heading">
            <div className="assistant-icon">
              <Sparkles size={17} />
            </div>
            <h2>실험 어시스턴트</h2>
            <button
              className="close-chat"
              aria-label="어시스턴트 닫기"
              onClick={() => setMobileChat(false)}
            >
              <X size={16} />
            </button>
          </header>
          <div className="chat-log" aria-live="polite">
            <div className="chat-byline">
              <span className="assistant-light" />
              PHYSIS AI
            </div>
            <div className="chat-bubble">
              궁금한 물리 현상을 물어보세요. 실험을 만들거나, 지금 보고 있는 실험의 조건을 바꿀 수
              있어요.
            </div>
            {experiment && (
              <div className="suggestions">
                <h3>이렇게 질문해 보세요</h3>
                {(experiment.model === 'free_fall'
                  ? ['물체 B의 질량을 10 kg으로 바꿔 줘', '두 물체의 낙하 시간을 비교해 줘']
                  : ['현재 실험 결과를 설명해 줘', '두 물체의 자유낙하를 보여 줘']
                ).map((p) => (
                  <button key={p} disabled={busy || hidden} onClick={() => void sendFromLab(p)}>
                    {p}
                    <ArrowUp size={13} />
                  </button>
                ))}
              </div>
            )}
            {hidden ? (
              <p className="chat-bubble discovery-note">
                탐구 중에는 예측을 기록한 뒤 결과를 공개하면 대화를 이어갈 수 있습니다.
              </p>
            ) : (
              (messages[experiment?.id ?? ''] ?? []).map((m, i) => (
                <div key={i} className={'message ' + m.role}>
                  <div className="chat-byline">
                    {m.role === 'user' ? '나'
                      : m.classification === 'needs_clarification' ? '조건 확인 필요'
                      : m.classification === 'assumptions' ? '가정 포함'
                      : m.unsupported || m.classification === 'unsupported' ? '지원 범위 안내'
                      : 'PHYSIS AI'}
                  </div>
                  <div className="chat-bubble">{m.text}</div>
                  {m.assumptions?.length ? (
                    <div className="chat-assumptions" aria-label="사용한 가정"
                      style={{ fontSize: '0.76rem', opacity: 0.82, marginTop: 5 }}>
                      사용한 가정 · {m.assumptions.join(' ')}
                    </div>
                  ) : null}
                </div>
              ))
            )}
            {!hidden && (messages[experiment?.id??'']??[]).length>0 && <button className="lab-evidence" onClick={()=>{setMode('explain');changeView('tutor')}}>튜터에서 답변 근거 보기</button>}
            <div ref={chatEnd} />
          </div>
          {notice && view==='lab' && <p role="status" className="lab-progress">{notice}</p>}
          <form
            className="chat-form"
            onSubmit={(ev: FormEvent) => {
              ev.preventDefault()
              void sendFromLab(draft)
            }}
          >
            <textarea
              aria-label="실험 질문"
              placeholder="실험에 대해 질문하세요…"
              maxLength={2000}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={!snapshot || hidden}
              onKeyDown={(ev) => {
                if (ev.key === 'Enter' && !ev.shiftKey && !ev.nativeEvent.isComposing) {
                  ev.preventDefault()
                  if (!busy && draft.trim()) void sendFromLab(draft)
                }
              }}
            />
            <div className="send-bar">
              <span>Shift + Enter 줄바꿈</span>
              {busy && aborter.current && <button type="button" aria-label="요청 취소" onClick={()=>aborter.current?.abort()}><X size={15}/></button>}
              <button
                type="submit"
                aria-label="보내기"
                title="보내기"
                disabled={busy || hidden || !draft.trim()}
              >
                <ArrowUp size={16} />
              </button>
            </div>
          </form>
          <div className="assistant-footer">
            <span>
              <i /> {(selection?.provider??provider) === 'mock' ? '로컬 규칙 모드 · Mock' : selection?.provider || provider || '연결 대기'}
            </span>
          </div>
        </aside>
        <main>
          {error && (
            <div role="alert" className="error-banner">
              <CircleAlert size={17} />
              <span>{error}</span>
              <button
                onClick={() => (snapshot ? void reopen(snapshot.experiment.id) : void init())}
              >
                다시 불러오기
              </button>
            </div>
          )}
          {view==='mathematics' ? (
            <Suspense fallback={<p role="status">수학 실험실을 여는 중입니다.</p>}>
              <MathematicsLab entry={mathEntry} snapshot={snapshot} catalog={catalog} numerical={()=>changeView('numerical')}
                open={(model,values,title,duration)=>{changeView('lab',false);void openModel(model,{initialValues:values,title,duration})}}/>
            </Suspense>
          ) : view==='research' ? (
            <ResearchView target={study} onTarget={setStudy} onModel={m=>{changeView('lab',false);void openModel(m)}}/>
          ) : view==='learning' ? (
            <LearningView onReview={async id=>{await reopen(id);setMode('review');changeView('tutor',false)}} onErase={erase}/>
          ) : !snapshot ? (
            <div className="loading pane">
              {busy ? <LoaderCircle className="spin" /> : <CircleAlert />}
              <h2>{busy ? '실험을 준비하고 있습니다' : '실험을 불러올 수 없습니다'}</h2>
            </div>
          ) : view==='tutor' ? (
            <TutorPanel snapshot={snapshot} level={level} onLevel={changeLevel} mode={mode}
              onMode={m=>{setMode(m);setLesson(null);setFocus([]);setNotice('');setPlaying(false)}}
              onFormula={id=>openStudy({tab:'registry',id})}
              onPrerequisite={id=>openStudy({tab:'roadmap',id:id==='functions'?'graphs':id==='dimensions'?'units':id})}
              lesson={lesson} busy={busy} notice={notice} onAsk={askTutor} onLab={()=>changeView('lab')}
              onCancel={()=>aborter.current?.abort()} scene={tutorScene}/>
          ) : view==='formula'||view==='numerical' ? (
            <Suspense fallback={<p role="status">공식과 계산 도구를 불러오는 중입니다.</p>}>
              <ScienceView tab={view} snapshot={snapshot} selectedVariable={focusVariable} onPatch={patch} onModel={openModel} onOpenLab={()=>changeView('lab')}/>
              {view==='numerical' && <button className="math-formula-link" onClick={()=>{
                setMathEntry({topic:'numerics'});changeView('mathematics',false)
              }}>근 찾기·차분·구적법 열기</button>}
              {view==='formula' && fromPhysics(snapshot) && <button className="math-formula-link" onClick={()=>{
                setMathEntry(fromPhysics(snapshot)!);changeView('mathematics',false)
              }}>이 공식으로 수학 실험 열기</button>}
            </Suspense>
          ) : (
            <>
              <div className="experiment-heading">
                <div>
                  <div className="experiment-kicker">
                    <span className="section-dash" />
                    {snapshot.experiment.category}
                    <span className="kicker-divider">/</span>
                    <span className="mono">
                      {snapshot.experiment.model.replaceAll('_', ' ').toUpperCase()}
                    </span>
                  </div>
                  <h1>{displayTitle}</h1>
                  <p>{snapshot.experiment.goal}</p>
                </div>
                <div className="heading-actions">
                  <button
                    onClick={toggleDiscovery}
                    className={discover ? 'accent' : ''}
                    aria-pressed={discover}
                  >
                    <Lightbulb size={15} />
                    개념 탐구
                  </button>
                  <button disabled={hidden} onClick={() => exportCsv(snapshot)}>
                    <ArrowDownToLine size={15} />
                    CSV 내보내기
                  </button>
                </div>
              </div>
              <ExperimentControls key={snapshot.experiment.id} title={displayTitle??snapshot.experiment.title} busy={busy}
                undo={available?.undo??0} redo={available?.redo??0} onRename={rename} onSave={saveFile}
                onLoad={()=>importer.current?.click()} onReset={resetInputs} onUndo={()=>void moveHistory('undo')} onRedo={()=>void moveHistory('redo')}/>
              <div className="work-grid">
                <div className="center-stack">
                  {discover && (
                    <section className="discovery pane">
                      <h2>
                        <Lightbulb size={17} />
                        개념 탐구
                      </h2>
                      <p>{snapshot.experiment.comparison}</p>
                      <label>
                        가설
                        <input
                          value={hypothesis}
                          disabled={revealed}
                          placeholder="어떤 관계가 있을까요?"
                          onChange={(ev) => setHypothesis(ev.target.value)}
                        />
                      </label>
                      <label>
                        예측
                        <input
                          value={prediction}
                          disabled={revealed}
                          placeholder="예상한 측정 결과를 기록하세요"
                          onChange={(ev) => setPrediction(ev.target.value)}
                        />
                      </label>
                      {revealed ? (
                        <label>
                          관찰과 결론
                          <textarea
                            placeholder="예측과 실제 결과를 비교하세요"
                            value={notes}
                            onChange={(ev) => setNotes(ev.target.value)}
                          />
                        </label>
                      ) : (
                        <button
                          className="primary"
                          disabled={!hypothesis.trim() || !prediction.trim()}
                          onClick={() => setRevealed(true)}
                        >
                          <Check size={15} />
                          결과 공개
                        </button>
                      )}
                    </section>
                  )}
                  {hidden ? (
                    <section className="locked pane">
                      <Microscope size={28} />
                      <h2>어떤 결과가 나올까요?</h2>
                      <p>가설과 예측을 기록하면 시뮬레이션과 측정값이 열립니다.</p>
                    </section>
                  ) : (
                    <>
                      <div className="simulation pane">
                        {scene}
                        <div className="playback">
                          <button
                            className="play"
                            title={playing ? '일시정지' : '재생'}
                            aria-label={playing ? '일시정지' : '재생'}
                            onClick={togglePlay}
                          >
                            {playing ? (
                              <Pause size={14} fill="currentColor" />
                            ) : (
                              <Play size={14} fill="currentColor" />
                            )}
                          </button>
                          <button
                            className="reset"
                            aria-label="처음으로"
                            title="처음으로"
                            onClick={() => seek(0)}
                          >
                            <RotateCcw size={16} />
                          </button>
                          <button
                            className="step"
                            aria-label="한 스텝"
                            title="한 스텝"
                            disabled={elapsed >= end}
                            onClick={nextFrame}
                          >
                            <StepForward size={16} />
                          </button>
                          <span className="time mono">
                            {elapsed.toFixed(2)} <small>s</small>
                          </span>
                          <input
                            aria-label="재생 시간"
                            className="scrubber"
                            type="range"
                            min="0"
                            max={end}
                            step="any"
                            value={elapsed}
                            onChange={(ev) => seek(Number(ev.target.value))}
                            style={{
                              background: `linear-gradient(to right,var(--lime) ${end ? (elapsed / end) * 100 : 0}%,#34414b 0)`,
                            }}
                          />
                          <small className="duration mono">{end.toFixed(2)} s</small>
                          <select
                            value={speed}
                            aria-label="재생 속도"
                            onChange={(ev) => setSpeed(Number(ev.target.value))}
                          >
                            {[0.25, 0.5, 1, 2, 4].map((v) => (
                              <option key={v} value={v}>
                                {v}×
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <Readings snapshot={snapshot} index={index} />
                      <FocusReadout snapshot={snapshot} index={index} focus={focus}/>
                      <GraphPanel
                        key={snapshot.experiment.id}
                        displayTitle={displayTitle}
                        snapshot={snapshot}
                        previous={previous}
                        index={index}
                        onSeek={seek}
                        focus={focus}
                      />
                      <CompareBench board={activeBoard??{anchor:snapshot.experiment.id,members:[snapshot],analysis:[]}} active={snapshot}
                        elapsed={elapsed} catalog={catalog} busy={busy} onSelect={selectMember} onClone={clone} onRemove={removeMember}
                        selection={comparison} onSelection={setComparison}/>
                    </>
                  )}
                </div>
                <div className="side-stack">
                  <Inspector
                    key={snapshot.experiment.id + ':' + snapshot.revision + ':' + formReset}
                    snapshot={snapshot}
                    busy={busy}
                    level={level}
                    hidden={hidden}
                    onPatch={patch}
                    onLevel={changeLevel} selectedVariable={focusVariable}
                  />
                  {!hidden && (
                    <div className="run-summary pane">
                      <h2>
                        <Activity size={16} />
                        계산 상태
                      </h2>
                      <div>
                        <span>물리 검증</span>
                        <b className={'status ' + status?.toLowerCase()}>
                          <i />
                          {statuses[snapshot.run.status]}
                        </b>
                      </div>
                      <div>
                        <span>계산 방법</span>
                        <b>{methods[snapshot.experiment.method]}</b>
                      </div>
                      <div>
                        <span>시간 간격</span>
                        <b className="mono">{numberText(snapshot.experiment.dt)} s</b>
                      </div>
                      <div>
                        <span>측정 표본</span>
                        <b className="mono">{snapshot.run.times.length}</b>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
          <div role="status" className={busy && snapshot ? 'working' : 'sr-only'}>
            {busy ? '계산 중…' : ''}
          </div>
        </main>
      </div>
      {drawer && (
        <Library
          drawer={drawer}
          onClose={() => setDrawer(null)}
          catalog={catalog}
          history={history}
          current={experiment?.id}
          busy={busy}
          onModel={m=>{changeView('lab',false);void openModel(m)}}
          onHistory={id=>{changeView('lab',false);void reopen(id)}}
        />
      )}
      {learningTools&&<ToolsDialog onClose={()=>setLearningTools(false)}>
        <LabLearningTools catalog={catalog} onStartPreset={preset=>{changeView('lab',false);void openModel(preset.model,preset)}}/>
      </ToolsDialog>}
      {settings&&<ProviderSettings selection={selection} onClose={()=>setSettings(false)} onSelect={s=>{
        setSelection(s);setProvider(s.provider);localStorage.setItem('physis-provider',JSON.stringify(s));setSettings(false)
      }}/>}
    </div>
  )
}
function FocusReadout({snapshot,index,focus}:{snapshot:Snapshot;index:number;focus:FocusAction[]}){
  const e=snapshot.experiment
  const object=focus.find(a=>a.op==='highlight_object')?.index??0
  const quantity=focus.find(a=>a.op==='highlight_quantity'||a.op==='highlight_graph')?.quantity
  const v=e.variables.find(v=>v.key===focus.find(a=>a.op==='highlight_variable')?.variable)
  const value=quantity?snapshot.run.series[object+'.'+quantity]?.[index]:undefined
  if(!v&&value===undefined&&!focus.some(a=>a.op==='highlight_object'))return null
  return <div className="focus-readout" aria-label="튜터가 강조한 측정값">
    <GraduationCap size={16}/><b>{e.objects[object]}</b>
    {quantity&&value!==undefined&&<span>{quantities[quantity]??quantity} <strong>{numberText(value)} {e.measurements[quantity]}</strong></span>}
    {v&&<mark>{v.label} = {numberText(e.values[v.key])} {v.unit}</mark>}
  </div>
}
function Readings({ snapshot, index }: { snapshot: Snapshot; index: number }) {
  const { experiment: e, run } = snapshot,
    q = defaultQuantity(snapshot)
  const metrics: [string, string, string][] = []
  if (e.model === 'free_fall') {
    metrics.push(
      ['0.y', '물체 A 높이', 'm'],
      ['1.y', '물체 B 높이', 'm'],
      ['0.vy', '수직 속도 A', 'm/s'],
    )
  } else {
    const choices = [
      q,
      ...(q === 'x'
        ? ['vx', 'ax']
        : q === 'y'
          ? ['vy', 'ay']
          : Object.keys(e.measurements).filter(
              (k) =>
                ![
                  'x',
                  'y',
                  'vx',
                  'vy',
                  'ax',
                  'ay',
                  'fx',
                  'fy',
                  'error',
                  'energy',
                  'ke',
                  'pe',
                ].includes(k),
            )),
      ...Object.keys(e.measurements),
    ]
    for (const k of new Set(choices)) {
      if (run.series['0.' + k]) metrics.push(['0.' + k, quantities[k] ?? k, e.measurements[k]])
      if (metrics.length === 3) break
    }
  }
  return (
    <section className="readings" aria-label="현재 측정값">
      {metrics.map(([key, label, unit], i) => (
        <div key={key} className="reading pane">
          <div>
            <i style={{ background: colors[key.startsWith('1.') ? 1 : i === 2 ? 2 : 0] }} />
            {label}
          </div>
          <p>
            <b>{numberText(run.series[key][index], 3)}</b>
            <small>{unit}</small>
          </p>
        </div>
      ))}
    </section>
  )
}
function Library({
  drawer,
  onClose,
  catalog,
  history,
  current,
  busy,
  onModel,
  onHistory,
}: {
  drawer: 'catalog' | 'history'
  onClose: () => void
  catalog: ModelSpec[]
  history: HistoryEntry[]
  current?: string
  busy: boolean
  onModel: (m: string) => void
  onHistory: (id: string) => void
}) {
  const [search, setSearch] = useState(''),
    dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const el = dialog.current
    el?.showModal()
    return () => el?.close()
  }, [])
  const result = catalog.filter((m) =>
    (m.title + m.category + m.model).toLowerCase().includes(search.trim().toLowerCase()),
  )
  return (
    <dialog
      ref={dialog}
      onCancel={onClose}
      className="library"
      onClick={(ev) => {
        if (ev.target === dialog.current) onClose()
      }}
      aria-labelledby="library-title"
    >
      <div>
        <header>
          <h2 id="library-title">
            {drawer === 'catalog' ? <Boxes size={19} /> : <History size={19} />}{' '}
            {drawer === 'catalog' ? '실험 목록' : '최근 실험'}
          </h2>
          <button onClick={onClose} aria-label="닫기">
            <X size={19} />
          </button>
        </header>
        {drawer === 'catalog' ? (
          <>
            <label className="search">
              <Search size={16} />
              <input
                autoFocus
                aria-label="실험 검색"
                placeholder="실험명 또는 분야 검색"
                value={search}
                onChange={(ev) => setSearch(ev.target.value)}
              />
            </label>
            <div className="model-list">
              {result.map((m) => (
                <button key={m.model} disabled={busy} onClick={() => onModel(m.model)}>
                  <span className="model-icon">
                    <Atom size={18} />
                  </span>
                  <span>
                    <small>{m.category}</small>
                    <b>{m.title}</b>
                    <em>{m.goal}</em>
                  </span>
                  <Plus size={16} />
                </button>
              ))}
              {result.length === 0 && <p>검색 결과가 없습니다.</p>}
            </div>
          </>
        ) : (
          <div className="model-list">
            {history.map((h) => (
              <button key={h.id} disabled={busy} onClick={() => onHistory(h.id)}>
                <Clock3 size={16} />
                <span>
                  <b>{h.title}</b>
                  <small>{h.id.slice(0, 8)}</small>
                </span>
                {h.id === current ? <Check size={17} /> : <ChevronRight size={17} />}
              </button>
            ))}
            {!history.length && <p>최근 실험이 없습니다.</p>}
          </div>
        )}
      </div>
    </dialog>
  )
}
