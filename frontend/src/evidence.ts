export interface Citation {
  id:string; doc_id:string; title:string; publisher:string; url:string; locator:string; license:string; quote:string; status:string
}
export interface CheckedValue {
  key:string; label:string; value:number; unit:string; experiment_id:string; revision:number; run_id:string
  status:string; reason?:string; expected?:number; expected_unit?:string; display_value?:string; expected_display?:string
}
export interface EvidenceClaim {
  kind:string; text:string; status:string; references:string[]; withheld?:boolean; withheld_reason?:string
  alignment?:{state:string;reason:string;references:string[]}; limits?:string[]
}
interface TeachingLevel {
  core:string;conditions:string[];misconception:string|null;follow_up:string|null;source_ids:string[]
  model_explanation?:string;model_limits?:string[];model_references?:string[]
}
export interface Evidence {
  answer_state?:string; generation?:string
  core:string; sources:Citation[]; theory_status:string; simulation_supported:boolean
  formula:{formula_id:string; title:string; latex:string; conditions:string[]; applicability:{status:string;reason:string};status:string} | null
  calculations:CheckedValue[]; checks:(Partial<CheckedValue>&{status:string})[]
  assumptions:string[]; uncertainty:string[]; claims:EvidenceClaim[]
  related_models:string[]; prerequisite:string|null
  awaiting_conditions?:boolean
  education?:{status:string;selected_level:string;levels:Record<string,TeachingLevel>}
  abstention?:{status:'none'|'partial'|'full';reasons:string[]}
}
export const evidenceLabels:Record<string,string> = {
  ANSWERED:'답변 완료',PARTIALLY_ANSWERED:'부분 답변',ASSUMPTION_REQUIRED:'가정을 사용한 답변',
  CLARIFICATION_REQUIRED:'추가 조건 필요',UNSUPPORTED_SIMULATION:'계산 모델 범위 밖',
  INSUFFICIENT_EVIDENCE:'근거 부족',VERIFICATION_FAILED:'검증 실패',
  source_verified:'근거 확인',calculation_verified:'계산 검증 통과',partial:'부분적으로 뒷받침',insufficient:'근거 부족',
  direct:'직접 뒷받침',related:'관련은 있으나 뒷받침하지 않음',contradiction:'근거와 모순',undecidable:'판단 불가능',
  registry_verified:'등록 정보 확인',model_explanation:'물리 모델 해설',
  conflict:'자료 충돌',failed:'검증 실패',unverifiable:'검증 불가능',applicable:'적용 조건 충족',outside_conditions:'적용 범위 밖',
}
export const displayStatus=(s:string)=>evidenceLabels[s]??s

export function formatEvidenceNumber(value:number,serverDisplay?:string) {
  if(serverDisplay)return serverDisplay
  if(!Number.isFinite(value))return '—'
  return Number(value.toPrecision(4)).toString()
}

export function claimReason(claim:EvidenceClaim) {
  return claim.withheld_reason || claim.alignment?.reason || ''
}

export function downloadReport(e:Evidence, question:string) {
  const paragraphs = ['# PHYSIS 실험 보고서',question,'## 핵심 설명',e.core]
  if (e.formula) paragraphs.push('## 공식',e.formula.title,'$$\n'+e.formula.latex+'\n$$',...e.formula.conditions,e.formula.applicability.reason)
  if(e.abstention && e.abstention.status!=='none')paragraphs.push('## 보류한 내용',...e.abstention.reasons)
  paragraphs.push('## 계산 기록',...e.calculations.map(v=>v.label+' '+formatEvidenceNumber(v.value,v.display_value)+' '+v.unit+' · 원수치 '+v.value+' · '+displayStatus(v.status)+' · '+v.experiment_id+' / v'+v.revision+' / '+v.run_id),
    '## 문헌 근거',...e.sources.map(s=>s.title+' · '+s.publisher+' · '+s.locator+' · '+s.id+'\n'+s.url+'\n> '+s.quote+'\n'+s.license),
    '## 주장별 근거',...e.claims.map(c=>[displayStatus(c.status)+(c.withheld?' · 본문 보류':''),c.text,claimReason(c),...c.references].filter(Boolean).join('\n')),
    '## 검증과 적용 범위',...e.checks.map(c=>displayStatus(c.status)+' · '+(c.label??'')+' '+(c.reason??'')),...e.assumptions,...e.uncertainty)
  const url=URL.createObjectURL(new Blob([paragraphs.join('\n\n')],{type:'text/markdown;charset=utf-8'}))
  const a=document.createElement('a');a.href=url;a.download='PHYSIS-실험보고서.md';a.click()
  setTimeout(()=>URL.revokeObjectURL(url),1000)
}
