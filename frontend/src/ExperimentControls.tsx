import {useEffect, useRef, useState, type ReactNode} from 'react'
import {FolderOpen, Redo2, Save, Undo2, RotateCcw} from 'lucide-react'

export function ExperimentControls({title, busy, undo, redo, onRename, onSave, onLoad, onReset, onUndo, onRedo}:{
  title:string; busy:boolean; undo:number; redo:number
  onRename:(name:string)=>void; onSave:()=>void; onLoad:()=>void; onReset:()=>void; onUndo:()=>void; onRedo:()=>void
}) {
  const [name,setName]=useState(title)
  useEffect(()=>setName(title),[title])
  return <section className="experiment-controls" aria-label="실험 파일과 변경 이력">
    <form onSubmit={event=>{event.preventDefault(); onRename(name.trim())}}>
      <label>실험 이름 <input maxLength={80} value={name} onChange={e=>setName(e.target.value)} /></label>
      <button disabled={busy || !name.trim() || name.trim()===title}>이름 적용</button>
    </form>
    <div>
      <button disabled={busy} title="Ctrl+S" onClick={onSave}><Save size={14}/>실험 저장</button>
      <button disabled={busy} title="Ctrl+O" onClick={onLoad}><FolderOpen size={14}/>실험 불러오기</button>
      <button disabled={busy || !undo} title="Ctrl+Z" onClick={onUndo}><Undo2 size={14}/>실행 취소</button>
      <button disabled={busy || !redo} title="Ctrl+Y" onClick={onRedo}><Redo2 size={14}/>다시 실행</button>
      <button disabled={busy} title="R" onClick={onReset}><RotateCcw size={14}/>조건 초기화</button>
    </div>
  </section>
}

export function ToolsDialog({children,onClose}:{children:ReactNode;onClose:()=>void}) {
  const ref=useRef<HTMLDialogElement>(null)
  useEffect(()=>{const el=ref.current; el?.showModal(); return ()=>el?.close()},[])
  return <dialog className="library learning-tools-dialog" aria-label="프리셋 및 단위 변환" ref={ref}
    onCancel={onClose} onClick={e=>{if(e.target===ref.current)onClose()}}>
    <div><header><h2>프리셋 및 단위 변환</h2><button onClick={onClose} aria-label="닫기">닫기</button></header>{children}</div>
  </dialog>
}

export function saveExperimentFile(contents:unknown, title:string) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(contents,null,2)],{type:'application/json'}))
  const a=document.createElement('a')
  a.href=url
  a.download='PHYSIS-'+title.replace(/[<>:"/\\|?*\u0000-\u001f]/g,'_').slice(0,80)+'.json'
  a.click()
  window.setTimeout(()=>URL.revokeObjectURL(url),1000)
}
