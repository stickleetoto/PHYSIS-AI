import { useState } from 'react'
import { ArrowRight, BookMarked, Check, CircleHelp, Download, FlaskConical, NotebookPen, Trash2 } from 'lucide-react'
import { levels, methods, statuses } from './domain'
import { clearLearning, exportLearning, latestJudgments, learningWarning, modeNames, useLearning, type LearningEvent } from './learning'
import './tutor.css'

const labels:Record<LearningEvent['kind'],string>={experiment:'실험',turn:'질문',hypothesis:'가설',observation:'관찰',conclusion:'결론',note:'메모',bookmark:'북마크',self:'자기 평가',answer:'복습 답변'}
type Filter='all'|'turn'|'experiment'|'inquiry'|'review'|'notes'
const groups:Record<Filter,{name:string;kinds:LearningEvent['kind'][]}> = {
  all:{name:'전체',kinds:[]},experiment:{name:'실험',kinds:['experiment']},turn:{name:'질문',kinds:['turn']},
  inquiry:{name:'탐구 기록',kinds:['hypothesis','observation','conclusion']},review:{name:'이해도',kinds:['answer','self']},
  notes:{name:'북마크·메모',kinds:['note','bookmark']},
}
const dateText=(date:string)=>new Date(date).toLocaleString('ko-KR',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})
function Details({e,all}:{e:LearningEvent;all:LearningEvent[]}) {
  if (e.kind==='turn') return <><b>{e.message}</b><p>{e.reply||'응답 내용 없음'}</p>{e.lesson && <small>{modeNames[e.lesson.mode]}</small>}</>
  if (e.kind==='experiment') return <><b>{e.title} · 버전 {e.revision}</b><p>{statuses[e.status]} · {methods[e.method]} · Δt {e.dt} s · 설정 시간 {e.duration} s</p>
    <details><summary>설정값과 계산 결과</summary><dl>{Object.entries(e.values).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      <dl>{Object.entries(e.facts).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl></details></>
  const parent=all.find(item=>item.id===e.parent)
  return <><b>{e.text}</b>{parent?.kind==='hypothesis' && <p>연결된 가설 · {parent.text}</p>}
    {e.kind==='answer'&&<p>선택한 답 · {e.chosen} · {e.verdict==='understood'?'정답':'오답'}<br/>{e.feedback}</p>}</>
}
export function LearningView({onReview,onErase}:{onReview:(id:string)=>void;onErase:()=>Promise<void>}) {
  const state=useLearning()
  const [filter,setFilter]=useState<Filter>('all')
  const [confirm,setConfirm]=useState(false)
  const [deleting,setDeleting]=useState(false)
  const [exporting,setExporting]=useState(false)
  const [error,setError]=useState('')
  const records=state.events
  const experiments=records.filter(e=>e.kind==='experiment')
  const topics=new Map(experiments.map(e=>[e.topic,e]))
  const judgments=latestJudgments(records)
  const understood=[...judgments.values()].filter(e=>e.verdict==='understood').length
  const review=[...judgments.values()].filter(e=>e.verdict==='review')
  const visible=[...records].reverse().filter(e=>filter==='all'||groups[filter].kinds.includes(e.kind))
  async function erase() {
    setDeleting(true)
    setError('')
    try {
      await onErase()
      clearLearning()
      setConfirm(false)
    } catch(e) {setError(e instanceof Error?e.message:'기록을 삭제할 수 없습니다. 다시 시도하세요.')}
    finally {setDeleting(false)}
  }
  async function download() {
    setExporting(true)
    setError('')
    try {await exportLearning()}
    catch(e) {setError(e instanceof Error?e.message:'학습 기록을 내보낼 수 없습니다.')}
    finally {setExporting(false)}
  }
  return <section className="tutor-page learning-page">
    <header className="edu-heading"><div><h1>학습 기록</h1><p>실험을 돌아보고, 다시 확인할 개념을 찾아보세요.</p></div>
      <div className="edu-controls"><button disabled={exporting||deleting} onClick={()=>void download()}><Download size={15}/> {exporting?'준비 중…':'JSON 내보내기'}</button>
        <button onClick={()=>setConfirm(!confirm)} disabled={deleting}><Trash2 size={15}/>전체 삭제</button></div>
    </header>
    {confirm && <section className="edu-delete" aria-label="학습 기록 삭제 확인"><b>이 기기의 PHYSIS 실험과 학습 기록을 모두 삭제할까요?</b><p>질문, 가설, 복습 답변, 북마크와 저장된 실험을 함께 삭제합니다. 필요하면 먼저 JSON으로 내보내세요.</p>
      <button disabled={deleting} onClick={()=>setConfirm(false)}>취소</button><button disabled={deleting} onClick={()=>void erase()}>{deleting?'삭제 중…':'삭제 확인'}</button></section>}
    {error && <p role="alert">{error}</p>}{learningWarning()&&<p role="alert">{learningWarning()}</p>}
    <section className="edu-stats" aria-label="학습 진도">
      <div><FlaskConical/><p>탐구한 개념</p><b>{topics.size}</b></div>
      <div><Check/><p>이해 표시</p><b>{understood}</b></div>
      <div><CircleHelp/><p>다시 볼 개념</p><b>{review.length}</b></div>
    </section>
    <div className="edu-layout"><section className="edu-card edu-log"><div className="edu-card-head"><NotebookPen size={19}/><h2>학습 일지</h2></div>
      <div className="edu-filter">{(Object.keys(groups) as Filter[]).map(k=><button key={k} aria-pressed={k===filter} onClick={()=>setFilter(k)}>{groups[k].name}</button>)}</div>
      {visible.length? <ol>{visible.map(e=><li key={e.id}><div className="edu-entry-meta"><span>{labels[e.kind]}</span><time dateTime={e.time}>{dateText(e.time)}</time></div>
        <Details e={e} all={records}/><footer>{e.title} · {levels[e.level]}{e.revision?` · v${e.revision}`:''}</footer></li>)}</ol>:
        <div className="edu-empty"><NotebookPen size={27}/><h3>{records.length?'이 분류에 기록이 없습니다':'첫 학습을 시작해 보세요'}</h3><p>튜터와 나눈 질문, 직접 세운 가설과 실험 결과가 이곳에 쌓입니다.</p></div>}
      </section><aside className="edu-sidebar"><section className="edu-card edu-concepts"><header><BookMarked size={18}/><h2>개념별 복습</h2></header>
        <p>최근 복습 답변이나 직접 표시한 이해도를 기준으로 정리합니다.</p>
        {topics.size===0 && <p>실험을 열면 개념이 표시됩니다.</p>}
        {[...topics].map(([topic,e])=>{const judgment=judgments.get(topic)
          return <div key={topic}><b>{e.title}</b><small>{judgment?`${judgment.kind==='answer'?'복습 답변':'자기 평가'} · ${judgment.verdict==='understood'?'이해 표시':'다시 보기'}`:'이해도 미확인'}</small>
            {e.experimentId && <button onClick={()=>onReview(e.experimentId!)}>복습 문제 열기<ArrowRight size={14}/></button>}</div>
        })}
      </section></aside></div>
  </section>
}
