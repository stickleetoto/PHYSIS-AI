import { lazy, Suspense } from 'react'
import { BookOpen, Network, Sigma } from 'lucide-react'
import Roadmap from './Roadmap'
const Formulas=lazy(()=>import('./FormulaLibrary'))
const Library=lazy(()=>import('./KnowledgeLibrary').then(m=>({default:m.KnowledgeLibrary})))
export type StudyTab='library'|'registry'|'roadmap'
export interface StudyTarget {tab:StudyTab; id?:string; math?:boolean}
export function ResearchView({target,onTarget,onModel}:{target:StudyTarget;onTarget:(s:StudyTarget)=>void;onModel:(m:string)=>void}) {
  return <section className="research-view"><nav aria-label="지식 탐구 도구">{([['library','문헌 자료실',BookOpen],['registry','공식 라이브러리',Sigma],['roadmap','학습 로드맵',Network]] as const).map(([k,name,Icon])=>
    <button key={k} aria-pressed={target.tab===k} onClick={()=>onTarget({tab:k})}><Icon size={16}/>{name}</button>)}</nav>
    <Suspense fallback={<p role="status">학습 도구를 불러오는 중입니다.</p>}>{target.tab==='library'?<Library onModel={onModel} onFormula={id=>onTarget({tab:'registry',id})}/>:target.tab==='registry'?
      <Formulas key={target.id??String(target.math)} onModel={onModel} initialId={target.id} initialTool={target.math}/>:<Roadmap key={target.id} initialTopic={target.id} onModel={onModel} onMath={()=>onTarget({tab:'registry',math:true})}/>}</Suspense></section>
}
