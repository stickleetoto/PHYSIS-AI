import { useState, type FormEvent } from 'react'
import { BookOpen, FileDown, Microscope } from 'lucide-react'
import { api } from './domain'
import { claimReason, displayStatus, downloadReport, formatEvidenceNumber, type Evidence, type EvidenceClaim, type CheckedValue } from './evidence'

interface Props {
  evidence:Evidence
  question:string
  onFormula:(id:string)=>void
  onPrerequisite:(topic:string)=>void
}
function ClaimRow({claim, sources}:{claim:EvidenceClaim;sources:Evidence['sources']}) {
  return <details className="ev-claim"><summary><span>{displayStatus(claim.status)}</span> {claim.text.slice(0,82)}</summary>
    <p>{claim.text}</p>{claimReason(claim)&&<p>{claimReason(claim)}</p>}
    {claim.references.map(ref=>{
      const source=sources.find(s=>s.id===ref)
      return source?<article key={ref}><small>{source.title} · {source.locator}</small><blockquote lang="en">{source.quote}</blockquote>
        <a href={source.url} target="_blank" rel="noreferrer">근거 원문 열기 ↗</a></article>:<small key={ref}>{ref} </small>
    })}</details>
}
export function EvidencePanel({evidence:e,question,onFormula,onPrerequisite}:Props) {
  const [tab,setTab]=useState('sources')
  const [key,setKey]=useState(''),[value,setValue]=useState(''),[unit,setUnit]=useState('')
  const [answer,setAnswer]=useState(''),[pending,setPending]=useState(false)
  const current=e.calculations.find(n=>n.key===key)??e.calculations[0]
  const failures=e.checks.filter(c=>c.status==='failed'||c.status==='conflict'||c.status==='unverifiable')
  const teaching=e.education?.levels[e.education.selected_level]
  const accepted=e.claims.filter(c=>!c.withheld)
  const withheld=e.claims.filter(c=>c.withheld)
  async function audit(event:FormEvent) {
    event.preventDefault()
    if(!current||!value.trim()||!Number.isFinite(Number(value)))return
    setPending(true)
    try {
      const payload={key:current.key,value:Number(value),unit:unit.trim()||current.unit,experiment_id:current.experiment_id,
        revision:current.revision,run_id:current.run_id}
      const r=await api<{calculations:CheckedValue[]}>('/evidence/check','POST',
        {experiment_id:current.experiment_id,revision:current.revision,query:question||'현재 실험',numbers:[payload]})
      const c=r.calculations[0]
      setAnswer(displayStatus(c.status)+' · '+c.reason+(c.expected===undefined?'':' 기준값 '+formatEvidenceNumber(c.expected,c.expected_display)+' '+c.expected_unit))
    }catch(err){setAnswer(err instanceof Error?err.message:'검산 요청 실패')}
    finally{setPending(false)}
  }
  return <section className="evidence-panel" aria-label="답변 근거">
    <header><div><BookOpen size={18}/><h3>답변 근거</h3></div><button onClick={()=>downloadReport(e,question)}><FileDown size={14}/> 보고서 저장</button></header>
    <div className="ev-summary"><span>이론 자료 · {e.awaiting_conditions?'조건 확인 중':e.theory_status==='available'?'확인':e.theory_status==='deferred'?'탐구 후 열람':'근거 부족'}</span>
      <span>시뮬레이션 · {e.awaiting_conditions?'입력 대기':e.simulation_supported?'연결됨':'미지원'}</span>
      {e.answer_state&&<span>답변 · {displayStatus(e.answer_state)}</span>}
      {e.generation==='verified_fallback'&&<span>내장 자료로 답변</span>}</div>
    {failures.map((c,i)=><p key={i} className="ev-alert" role="alert">{displayStatus(c.status)} · {c.label} {c.value!==undefined&&'제안값 '+formatEvidenceNumber(c.value,c.display_value)+' '+c.unit+' · '}{c.expected!==undefined&&'기준값 '+formatEvidenceNumber(c.expected,c.expected_display)+' '+c.expected_unit+' · '}{c.reason}</p>)}
    {e.prerequisite&&<button className="ev-link" onClick={()=>onPrerequisite(e.prerequisite!)}>선행 개념 학습 열기</button>}
    <div className="ev-tabs" aria-label="근거 종류">{[['sources','문헌 근거'],['formula','공식과 가정'],['numbers','계산 검증'],['coverage','주장별 근거']].map(([k,v])=><button key={k} aria-pressed={k===tab} onClick={()=>setTab(k)}>{v}</button>)}</div>
    {tab==='sources'&&<div>{e.sources.length===0?<p>{e.uncertainty[0]}</p>:e.sources.map(s=><article key={s.id}>
      <small>{s.publisher} · {displayStatus(s.status)}</small><h4>{s.title}</h4><p>{s.locator}</p>
      <blockquote lang="en">{s.quote}</blockquote>{e.claims.filter(c=>c.kind==='reviewed_paraphrase'&&c.references.includes(s.id)).map(c=><p key={c.text}><small>한국어 풀이 · {displayStatus(c.status)}</small><br/>{c.text}</p>)}<footer><small>{s.license}</small><a href={s.url} target="_blank" rel="noreferrer">원문 열기 ↗</a></footer></article>)}</div>}
    {tab==='formula'&&<div>{e.formula?<><h4>{e.formula.title}</h4><p>{displayStatus(e.formula.applicability.status)} · {e.formula.applicability.reason}</p>
      <ul>{e.formula.conditions.map(x=><li key={x}>{x}</li>)}</ul>
      <button className="ev-link" onClick={()=>onFormula(e.formula!.formula_id)}>공식과 단위 열기</button></>:<p>이 답변에 연결된 공식이 없습니다.</p>}
      {e.assumptions.length>0&&<><h4>계산 가정</h4><p>{e.assumptions.join(' · ')}</p></>}</div>}
    {tab==='numbers'&&<div>{current?<><dl className="ev-readings">{e.calculations.map(c=><div key={c.key}><dt>{c.label}</dt><dd>{formatEvidenceNumber(c.value,c.display_value)} {c.unit}{c.status!=='calculation_verified'&&<small> · {displayStatus(c.status)}</small>}</dd></div>)}</dl>
      <small>실험 {current.experiment_id} · 버전 {current.revision} · 실행 {current.run_id}</small>
      <form onSubmit={audit}><h4><Microscope size={15}/> 설명 속 수치 검산</h4>
      <label>물리량<select value={current.key} onChange={ev=>{setKey(ev.target.value);setAnswer('');setUnit('')}}>{e.calculations.map(n=><option key={n.key} value={n.key}>{n.label}</option>)}</select></label>
      <label>설명에 적힌 값<input required aria-label="설명에 적힌 값" type="number" step="any" value={value} onChange={ev=>setValue(ev.target.value)}/></label>
      <label>설명에 적힌 단위<input aria-label="설명에 적힌 단위" maxLength={32} placeholder={current.unit} value={unit} onChange={ev=>setUnit(ev.target.value)}/></label>
      <button disabled={pending||!value.trim()}>실제 실행과 대조</button></form>{answer&&<p role="status">{answer}</p>}</>:<p>이 질문에는 검산할 실행 결과가 없습니다.</p>}</div>}
    {tab==='coverage'&&<div>
      {e.abstention && e.abstention.status!=='none' && <details><summary>{e.abstention.status==='full'?'답변을 보류한 이유':'일부 설명을 보류한 이유'}</summary>
        <ul>{e.abstention.reasons.map(reason=><li key={reason}>{reason}</li>)}</ul></details>}
      {accepted.filter(c=>c.kind!=='quotation').map((c,i)=><ClaimRow key={i} claim={c} sources={e.sources}/>)}
      {withheld.length>0&&<details className="ev-history"><summary>검토에서 보류한 문장 {withheld.length}개</summary>
        {withheld.map((c,i)=><ClaimRow key={i} claim={c} sources={e.sources}/>)}</details>}
      {accepted.some(c=>c.kind==='quotation')&&<details className="ev-history"><summary>대조한 원문 인용</summary>
        {accepted.filter(c=>c.kind==='quotation').map(c=><ClaimRow key={c.references.join('/')} claim={c} sources={e.sources}/>)}</details>}
      {teaching?.misconception&&<p><strong>다시 생각해 보기</strong> · {teaching.misconception}</p>}
      {teaching?.follow_up&&<p><strong>이해도 확인</strong> · {teaching.follow_up}</p>}
      {e.uncertainty.map(t=><p key={t}>{t}</p>)}</div>}
  </section>
}
