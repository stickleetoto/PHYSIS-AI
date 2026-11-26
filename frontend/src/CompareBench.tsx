import {useState} from 'react'
import {CopyPlus, Download, GitCompareArrows, X} from 'lucide-react'
import {colors, exportCsv, methods, numberText, quantities, range, sampleIndex, samples, statuses, type ModelSpec, type Snapshot} from './domain'
import {displayedComparison, type Board, type ComparisonSelection} from './bench'

export function CompareBench({board, active, elapsed, catalog, busy, onSelect, onClone, onRemove, selection, onSelection}:{
  board:Board; active:Snapshot; elapsed:number; catalog:ModelSpec[]; busy:boolean
  onSelect:(s:Snapshot)=>void; onClone:(model?:string)=>void; onRemove:(id:string)=>void
  selection: ComparisonSelection; onSelection:(next: ComparisonSelection)=>void
}) {
  const [chosen,setChosen]=useState('')
  const {members}=board
  const {choices,count,quantity,object_index:object}=displayedComparison(members,active,selection)
  const q=quantity??''
  const key=object+'.'+q
  const unit=members[0].experiment.measurements[q]
  const last=Math.max(...members.map(s=>s.run.times.at(-1)??0), .001)
  const [low,high]=range(members.flatMap(s=>s.run.series[key]??[]))
  const x=(t:number)=>54+t/last*594, y=(v:number)=>132-(v-low)/(high-low)*100
  return <section className="pane multi-bench" aria-label="다중 실험 비교">
    <header className="panel-heading"><h2><GitCompareArrows size={17}/>비교 워크벤치</h2><span className="mono">{members.length} / 4</span></header>
    <div className="bench-tools">
      <button disabled={busy||members.length>=4} onClick={()=>onClone()}><CopyPlus size={15}/>현재 실험 복제</button>
      <select aria-label="비교할 다른 모델" value={chosen} onChange={e=>setChosen(e.target.value)}>
        <option value="">다른 모델 선택</option>{catalog.map(s=><option key={s.model} value={s.model}>{s.title}</option>)}
      </select><button disabled={!chosen||busy||members.length>=4} onClick={()=>onClone(chosen)}>비교에 추가</button>
    </div>
    {members.length>1&&<>
      <div className="bench-cards">{members.map((s,i)=>{
        const id=s.experiment.id, t=s.run.times, index=sampleIndex(t,elapsed), value=s.run.series[key]?.[index]
        return <div className={'bench-member '+(id===active.experiment.id?'current':'')} key={id} style={{borderTopColor:colors[i]}}>
          <button className="bench-select" aria-pressed={id===active.experiment.id} onClick={()=>onSelect(s)} disabled={busy}>
            <b>{i===0?'기준':'비교 '+i} · {board.display_names?.[id] || s.experiment.title}</b>
            <small>{methods[s.experiment.method]} · {statuses[s.run.status]}</small>
          </button>
          <div className="bench-value">{value!==undefined&&<strong>{numberText(value)} <small>{unit}</small></strong>}
            <small>{numberText(t[index])} s {elapsed>(t.at(-1)??0)?'· 관찰 종료':''}</small></div>
          <div className="member-tools"><button onClick={()=>exportCsv(s)} aria-label={'실험 '+(i+1)+' CSV'}><Download size={13}/>CSV</button>
            {i>0&&<button disabled={busy} aria-label={'비교 '+i+' 제외'} onClick={()=>onRemove(id)}><X size={13}/>제외</button>}</div>
        </div>
      })}</div>
      {q?<><div className="bench-tools">
        <label>공통 물리량 <select aria-label="공통 물리량" value={q} onChange={e=>onSelection({...selection,quantity:e.target.value})}>
          {choices.map(k=><option key={k} value={k}>{quantities[k]??k} ({members[0].experiment.measurements[k]})</option>)}</select></label>
        {count>1&&<select aria-label="비교할 물체" value={object} onChange={e=>onSelection({...selection,object_index:Number(e.target.value)})}>
          {members[0].experiment.objects.slice(0,count).map((n,i)=><option key={n} value={i}>{n}</option>)}</select>}
      </div>
      <svg role="img" aria-label="공통 시간축 비교 그래프" viewBox="0 0 670 168" className="plot-svg">
        {[0,.5,1].map(f=><g key={f}><path d={`M54 ${132-100*f}H648`} stroke="#35434b" strokeDasharray="3 4"/>
          <text x="48" y={135-100*f} textAnchor="end">{numberText(low+(high-low)*f)}</text>
          <text x={x(last*f)} y="151" textAnchor="middle">{numberText(last*f)}</text></g>)}
        <text x="55" y="18">{quantities[q]??q} ({unit})</text><text x="650" y="164" textAnchor="end">t (s)</text>
        {members.map((s,i)=>{const v=s.run.series[key]; if(!v)return null
          const d=samples(v.length,400).map((j,n)=>(n?'L':'M')+x(s.run.times[j])+','+y(v[j])).join(' ')
          return <path key={s.experiment.id} d={d} fill="none" stroke={colors[i]} strokeWidth="2.4" strokeDasharray={['','6 3','3 3','12 3 3 3'][i]}/>
        })}<path d={`M${x(elapsed)} 25V132`} stroke="#d5e7ef" strokeDasharray="3 3"/>
      </svg></>:<p>공통 단위의 측정량이 없습니다. 각 실험의 그래프를 따로 확인하세요.</p>}
      <ul className="comparison-notes">{board.analysis.map((msg,i)=><li key={i}><b>비교 {i+1}</b> {msg}</li>)}</ul>
    </>}
  </section>
}
