import { useState, type FormEvent, type ReactNode } from 'react'
import { ArrowRight, ArrowUp, BookOpen, Bookmark, Check, ClipboardCheck, Compass, FlaskConical, FunctionSquare, GraduationCap, Lightbulb, MessageCircle, Pause, PencilLine } from 'lucide-react'
import { defaultQuantity, levels, numberText, quantities, type Level, type Snapshot } from './domain'
import { addEvidence, learningWarning, modeNames, recallLearning, recordTurn, useLearning, type Lesson, type TutorMode } from './learning'
import './tutor.css'
import { EvidencePanel } from './EvidencePanel'
export type {Lesson,TutorMode,VisualAction} from './learning'

const icons = {explain:BookOpen,experiment:FlaskConical,discovery:Compass,equation:FunctionSquare,review:ClipboardCheck}
const intro:Record<TutorMode,string> = {
  explain:'그래프를 따라 물체가 어떻게 움직이는지 살펴보세요.',
  experiment:'바꿀 변수와 고정할 조건을 정하고 실험을 시작하세요.',
  discovery:'예상을 먼저 기록하고, 실험에서 관찰한 결과와 비교하세요.',
  equation:'변수와 단위, 식을 유도한 과정과 적용 조건을 살펴보세요.',
  review:'현재 실험에 관한 한 문제를 풀고 답의 근거를 확인하세요.',
}
interface Props {
  snapshot:Snapshot|null
  level:Level
  mode:TutorMode
  onLevel:(level:Level)=>void
  onMode:(mode:TutorMode)=>void
  lesson:Lesson|null
  busy:boolean
  onAsk:(message:string)=>void
  onLab:()=>void
  scene?:ReactNode
  onCancel?:()=>void
  notice?:string
  onFormula:(id:string)=>void
  onPrerequisite:(topic:string)=>void
}
export function TutorPanel(props:Props) {
  const {snapshot:s,level,mode,onLevel,onMode,lesson,busy,onAsk,onLab,scene,onCancel,notice}=props
  const state=useLearning()
  const [draft,setDraft]=useState('')
  const [writing,setWriting]=useState('')
  const [note,setNote]=useState('')
  const [showNotes,setShowNotes]=useState(false)
  const id=s?.experiment.id
  const items=state.events.filter(e=>e.experimentId===id)
  const turns=items.filter(e=>e.kind==='turn')
  const last=turns.filter(e=>e.lesson?.mode===mode && e.revision===s?.revision && e.level===level).at(-1)
  const active=last?.lesson??(lesson?.mode===mode?lesson:null)
  const questions=[...state.events].reverse().filter(e=>e.kind==='turn' && (e.experimentId===id || !e.experimentId))
  const hypothesis=items.filter(e=>e.kind==='hypothesis').at(-1)
  const observation=hypothesis && items.find(e=>e.kind==='observation' && e.parent===hypothesis.id)
  const conclusion=hypothesis && items.find(e=>e.kind==='conclusion' && e.parent===hypothesis.id)
  // An open prediction can be tested against a new revision of the same experiment.
  const predicted=!!hypothesis && (hypothesis.revision===s?.revision || !conclusion || conclusion.revision===s?.revision)
  const concealed=mode==='discovery' && !predicted
  const quiz=active?.review
  const answer=items.filter(e=>e.kind==='answer').filter(e=>e.kind==='answer' && e.text===quiz?.question && e.revision===s?.revision).at(-1)
  const bookmarked=items.some(e=>e.kind==='bookmark' && e.revision===s?.revision)
  const q=s && defaultQuantity(s)
  function send(e:FormEvent) {
    e.preventDefault()
    if (!draft.trim()||busy) return
    const question=draft.trim()
    const memory=s && recallLearning(question,s,mode)
    if (s && memory) recordTurn(question,memory,s,level)
    else onAsk(question)
    setDraft('')
  }
  function evidence(kind:'hypothesis'|'observation'|'conclusion') {
    if (!s || !writing.trim()) return
    addEvidence(s,level,kind,writing,kind==='hypothesis'?{}:{parent:hypothesis?.id})
    setWriting('')
  }
  function changeMode(value:TutorMode) {
    setWriting('')
    onMode(value)
  }
  return <section className="tutor-page">
    <header className="edu-heading"><div><h1>물리 튜터</h1><p>질문에서 출발해 직접 확인하는 물리 실험</p></div>
      <label className="edu-level"><GraduationCap size={17}/> 학습 수준
        <select value={level} disabled={busy} onChange={e=>onLevel(e.target.value as Level)}>{Object.entries(levels).map(([v,n])=><option key={v} value={v}>{n}</option>)}</select>
      </label></header>
    <nav className="edu-modes" aria-label="튜터 모드">{(Object.keys(modeNames) as TutorMode[]).map(m=>{
      const Icon=icons[m]
      return <button key={m} aria-pressed={m===mode} disabled={busy} onClick={()=>changeMode(m)}><Icon size={17}/>{modeNames[m]}</button>
    })}</nav>
    <div className="edu-layout">
      <section className="edu-card tutor-dialog" aria-label="튜터 대화">
        <header className="edu-card-head"><span className="edu-mark"><Lightbulb size={19}/></span><div><small>{modeNames[mode]}</small><h2>{active?.title??s?.experiment.title??'무엇이 궁금한가요?'}</h2></div></header>
        {last && <div className="edu-current-question"><MessageCircle size={14}/>{last.message}</div>}
        <div className="edu-reading" role={active?.evidence?.simulation_supported===false?'status':undefined}>{(active?.text??(mode==='explain'&&s?s.explanation:intro[mode])).split(/\n\n/).map((p,i)=><p key={i}>{p}</p>)}</div>
        {active?.prompt && !active.text.includes(active.prompt) && <p className="edu-prompt">{active.prompt}</p>}
        {active?.evidence && !concealed && mode!=='review' &&
          <EvidencePanel key={last?.id??active.title} evidence={active.evidence} question={last?.message??''}
            onFormula={props.onFormula} onPrerequisite={props.onPrerequisite}/>}
        {mode==='review'&&s&&quiz && <div className="edu-quiz" aria-label="복습 답변">
          {quiz.options.map((option,i)=><button key={option} onClick={()=>addEvidence(s,level,'answer',quiz.question,{
            verdict:i===quiz.correct?'understood':'review',chosen:option,feedback:quiz.feedback,
          })}><span>{i+1}</span>{option}</button>)}
          {answer?.kind==='answer' && <aside role="status"><strong>{answer.verdict==='understood'?'정답입니다':'다시 생각해 보세요'}</strong><p>선택한 답 · {answer.chosen}</p><p>{answer.feedback}</p></aside>}
        </div>}
        {mode==='discovery' && s && <section className="edu-inquiry">
          {predicted && hypothesis?.kind==='hypothesis' && <p><strong>내 가설</strong>{hypothesis.text}</p>}
          {predicted && observation?.kind==='observation' && <p><strong>내 관찰</strong>{observation.text}</p>}
          {predicted && conclusion?.kind==='conclusion' && <p><strong>내 결론</strong>{conclusion.text}</p>}
          {(() => {
            const stage=!predicted||conclusion?'hypothesis':observation?'conclusion':'observation'
            const label={hypothesis:conclusion?'새 가설':'내 가설',observation:'관찰 결과',conclusion:'결론'}[stage]
            return <div><label>{label}<textarea key={stage} value={writing} onChange={e=>setWriting(e.target.value)} maxLength={2000} placeholder={
              stage==='hypothesis'?'무엇이 달라질까요? 그렇게 생각한 이유도 적어 보세요.':stage==='observation'?'장면이나 그래프에서 확인한 변화와 측정값을 적어 보세요.':'예상과 관찰이 일치했나요? 근거를 적어 보세요.'
            }/></label><button className="edu-action" disabled={!writing.trim()} onClick={()=>evidence(stage)}><PencilLine size={14}/>{label} 기록</button></div>
          })()}
        </section>}
        {!active && mode!=='discovery' && <div className="edu-suggestions">
          {(s?[{label:mode==='review'?'복습 문제 풀기':mode==='equation'?'공식 유도 보기':'현재 실험 살펴보기',message:'현재 실험 결과를 설명해 줘'}]:[
            {label:'두 공은 함께 떨어질까?',message:'자유낙하에서 무거운 공이 먼저 떨어질까?'},
            {label:'진자의 길이와 주기',message:'진자 실험을 만들어 줘'},
          ]).map(p=><button key={p.label} disabled={busy} onClick={()=>onAsk(p.message)}>{p.label}<ArrowRight size={14}/></button>)}
        </div>}
        {notice && <p role="status" className="edu-notice">{notice}</p>}
        <form className="edu-composer" onSubmit={send}><label className="sr-only" htmlFor="tutor-question">튜터에게 질문</label>
          <textarea id="tutor-question" placeholder={s?'이 실험에서 궁금한 점을 물어보세요…':'예: 같은 높이에서 떨어지는 두 공의 운동을 보여 줘'} maxLength={2000} rows={2}
            value={draft} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.form?.requestSubmit()}}}/>
          {busy&&onCancel?<button type="button" title="요청 취소" aria-label="요청 취소" onClick={onCancel}><Pause size={17}/></button>:<button type="submit" title="질문 보내기" aria-label="질문 보내기" disabled={busy||!draft.trim()}><ArrowUp size={18}/></button>}
        </form>
      </section>
      <aside className="edu-sidebar">
        <section className="edu-card tutor-scene"><header><div><small>연결된 실험</small><h2>{s?.experiment.title??'실험 장면'}</h2></div><FlaskConical size={19}/></header>
          {active?.evidence && !active.evidence.simulation_supported?<div className="edu-scene-message"><BookOpen size={24}/><p>이 질문에 연결된 시뮬레이션이 없습니다.</p></div>:
           concealed?<div className="edu-scene-message"><Compass size={24}/><p>예측을 기록하면 실험 장면과 측정값이 열립니다.</p></div>:
            scene??<div className="edu-scene-message"><FlaskConical size={24}/><p>질문으로 실험을 시작하세요.</p></div>}
          {s && !concealed && active?.evidence?.simulation_supported!==false && <>{q&&s.run.series['0.'+q]?.length>0 && <div className="edu-measure"><span>마지막 표본 · {quantities[q]??q}</span><b>{numberText(s.run.series['0.'+q].at(-1)!)} <small>{s.experiment.measurements[q]}</small></b></div>}
            <button className="edu-full-link" onClick={onLab}>실험실에서 변수 조작 <ArrowRight size={16}/></button></>}
        </section>
        {s && <section className="edu-card edu-notes"><h2>내 학습 메모</h2><div className="edu-controls">
          <button disabled={bookmarked} onClick={()=>addEvidence(s,level,'bookmark',s.experiment.title)}>{bookmarked?<Check size={14}/>:<Bookmark size={14}/>} {bookmarked?'북마크됨':'북마크'}</button>
          <button onClick={()=>setShowNotes(!showNotes)}><PencilLine size={14}/>메모 쓰기</button></div>
          {showNotes && <label>실험 메모<textarea value={note} maxLength={2000} onChange={e=>setNote(e.target.value)}/><button className="edu-action" disabled={!note.trim()} onClick={()=>{addEvidence(s,level,'note',note);setNote('');setShowNotes(false)}}>메모 저장</button></label>}
          <details><summary>내 이해도 표시</summary><div className="edu-controls">{(['understood','review'] as const).map(v=><button key={v} onClick={()=>addEvidence(s,level,'self',v==='understood'?'스스로 설명할 수 있음':'다시 살펴볼 개념',{verdict:v})}>{v==='understood'?'설명할 수 있어요':'다시 볼래요'}</button>)}</div></details>
        </section>}
      </aside>
    </div>
    {!concealed && questions.length>0 && <details className="edu-history"><summary>이전 질문과 대답 ({questions.length})</summary>{questions.map(e=>e.kind==='turn' && <article key={e.id}><b>{e.message}</b><p>{e.reply}</p></article>)}</details>}
    {learningWarning()&&<p role="alert">{learningWarning()}</p>}
  </section>
}
