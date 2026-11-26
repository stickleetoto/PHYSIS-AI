import { useEffect, useState, type FormEvent } from 'react'
import { api } from './domain'
import './knowledge-library.css'

interface Publication {
  id: string
  source_id: string
  title: string
  book: string
  chapter: string
  publisher: string
  author: string
  level: string
  url: string
  license: string
  license_url: string
  formulas: string
  tables: string
  citable: boolean
  models: string[]
  concepts: string[]
  chunk_count: number
  downloaded: string
  version: string
  sha256: string
}
interface Passage { id: string; doc_id: string; text: string; locator: string; url: string }
interface Detail extends Publication { chunks: Passage[]; related: Publication[] }
interface Row { doc: Publication; preview?: Passage }
interface Card { formula_id: string; title: string; latex: string }
const sources: Record<string, string> = {
  college: 'OpenStax · College Physics 2e', university1: 'OpenStax · University Physics 1',
  university2: 'OpenStax · University Physics 2', glenn: 'NASA Glenn', ntrs: 'NASA NTRS',
}
const levelLabels: Record<string,string> = {school: '중·고등', university: '대학'}
const errorMessage = (error: unknown) => error instanceof Error ? error.message : '자료를 불러오지 못했습니다.'

export function KnowledgeLibrary({onModel, onFormula}: {onModel: (model: string) => void; onFormula?: (model: string) => void}) {
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [level, setLevel] = useState('')
  const [rows, setRows] = useState<Row[]>([])
  const [selected, setSelected] = useState('')
  const [detail, setDetail] = useState<Detail | null>(null)
  const [focus, setFocus] = useState('')
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [cards, setCards] = useState<Card[]>([])
  const [modelNames, setModelNames] = useState<Record<string,string>>({})
  const [count, setCount] = useState<{documents: number; chunks: number} | null>(null)

  useEffect(() => {
    let active = true
    api<{documents: number; chunks: number}>('/knowledge/stats').then(x => { if (active) setCount(x) }).catch(() => {})
    api<{items: Card[]}>('/formulas').then(x => { if (active) setCards(x.items) }).catch(() => {})
    api<{models: {model: string; title: string}[]}>('/catalog').then(x => {
      if (active) setModelNames(Object.fromEntries(x.models.map(m => [m.model, m.title])))
    }).catch(() => {})
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    const params = new URLSearchParams()
    if (query) params.set('q',query)
    if (source) params.set('source',source)
    if (level) params.set('level',level)
    setBusy(true); setError(''); setDetail(null); setSelected(''); setFocus('')
    async function load() {
      const [catalog, results] = await Promise.all([
        api<{items: Publication[]}>('/knowledge/documents?' + params),
        query ? api<{items: (Publication & Passage)[]}>('/knowledge/search?' + params + '&limit=50') : null,
      ])
      const unique = new Map<string,Row>()
      for (const hit of results?.items ?? []) {
        if (!unique.has(hit.doc_id)) unique.set(hit.doc_id, {doc: {...hit, id: hit.doc_id}, preview: hit})
      }
      for (const doc of catalog.items) {
        if (!unique.has(doc.id)) unique.set(doc.id, {doc})
      }
      if (active) {
        const items = [...unique.values()]
        setRows(items); setSelected(items[0]?.doc.id || ''); setFocus(items[0]?.preview?.id || '')
      }
    }
    load().catch(e => { if (active) { setError(errorMessage(e)); setRows([]) } }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [query, source, level])

  useEffect(() => {
    if (!selected) return
    let active = true
    setDetail(null); setDetailError('')
    api<Detail>('/knowledge/documents/' + encodeURIComponent(selected)).then(d => {
      if (active) setDetail(d)
    }).catch(e => { if (active) setDetailError(errorMessage(e)) })
    return () => { active = false }
  }, [selected])

  function search(event: FormEvent) {
    event.preventDefault()
    setQuery(input.trim())
  }
  function choose(id: string, chunk = '') {
    setSelected(id); setFocus(chunk)
  }
  const paragraphs = detail ? [...detail.chunks].sort((a,b) => Number(b.id === focus) - Number(a.id === focus)) : []
  return <section className="knowledge-library">
    <header className="kl-head"><h2>지식 서재</h2>
      {count && <p>과학 자료 {count.documents}개 · 인용 가능한 원문 {count.chunks}문단</p>}
    </header>
    <form className="kl-controls" onSubmit={search}>
      <label className="kl-query">문헌 검색<input type="search" aria-label="과학 문헌 검색" placeholder="개념, 기호 또는 문헌 제목" value={input}
        onChange={e => {setInput(e.target.value); if (!e.target.value) setQuery('')}} maxLength={400}/></label>
      <label>자료 출처<select aria-label="자료 출처" value={source} onChange={e => setSource(e.target.value)}>
        <option value="">모든 출처</option>{Object.entries(sources).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
      </select></label>
      <label>자료 수준<select aria-label="자료 수준" value={level} onChange={e => setLevel(e.target.value)}>
        <option value="">모든 수준</option>{Object.entries(levelLabels).map(([k,v])=><option key={k} value={k}>{v}</option>)}
      </select></label>
      <button type="submit" className="kl-submit">검색</button>
    </form>
    {error && <p role="alert">{error}</p>}
    <div className="kl-columns">
      <section className="kl-list" aria-label="과학 자료 목록">
        <h3>{query ? '검색 결과' : '자료 목록'} <small>{busy ? '검색 중…' : rows.length + '개'}</small></h3>
        {!busy && !rows.length && <p>일치하는 자료가 없습니다.</p>}
        {!busy && rows.map(({doc,preview}) => <button key={doc.id} type="button" className="kl-item" aria-pressed={selected === doc.id}
          onClick={() => choose(doc.id, preview?.id)}>
          <small>{sources[doc.source_id] || doc.publisher}</small>
          <strong lang="en">{doc.title}</strong>
          <span>{doc.citable ? doc.chunk_count + '개 원문 문단' : '서지 정보'} · {levelLabels[doc.level] || doc.level}</span>
        </button>)}
      </section>
      <article className="kl-detail" aria-label="문헌 상세" aria-busy={!!selected && !detail && !detailError}>
        {detailError && <p role="alert">{detailError}</p>}
        {detail && <>
          <span className="kl-book">{detail.book} {detail.chapter && ' / ' + detail.chapter}</span>
          <h3 lang="en">{detail.title}</h3>
          <p>{detail.author} · {detail.publisher}</p>
          <div className="kl-links"><a href={detail.url} target="_blank" rel="noreferrer">원본 문서 ↗</a>
            <a href={detail.license_url} target="_blank" rel="noreferrer">{detail.citable ? detail.license : '서지 정보 · 원문 이용 조건'} ↗</a></div>
          {detail.citable ? <><h4>원문 미리보기</h4>
            {(detail.formulas.includes('present') || detail.tables.includes('present')) &&
              <p>영어 본문 발췌입니다. {detail.formulas.includes('present') && '수식의 전체 표기는 원본 문서에서 볼 수 있습니다. '}
                {detail.tables.includes('present') && '원문에 포함된 표는 발췌에서 제외했습니다.'}</p>}</> :
            <p className="kl-note">제목과 출처를 수록한 서지 레코드입니다. 본문은 원본 문서에서 열 수 있습니다.</p>}
          {paragraphs.map(p => <figure key={p.id} className={p.id === focus ? 'kl-quote current' : 'kl-quote'}>
            <blockquote lang="en">{p.text}</blockquote><figcaption>{p.locator} · <a href={p.url} target="_blank" rel="noreferrer">원문 위치 ↗</a></figcaption>
          </figure>)}
          {detail.models.length > 0 && <><h4>관련 실험</h4><div className="kl-actions">{detail.models.map(m =>
            <button key={m} onClick={() => onModel(m)}>{modelNames[m] || m} 실험</button>)}</div></>}
          {cards.some(c => detail.models.includes(c.formula_id)) && <><h4>관련 공식</h4><div className="kl-actions">
            {cards.filter(c => detail.models.includes(c.formula_id)).map(c => onFormula ?
              <button key={c.formula_id} onClick={() => onFormula(c.formula_id)}>{c.title} 공식</button> :
              <details key={c.formula_id}><summary>{c.title}</summary><code>{c.latex}</code></details>)}</div></>}
          {detail.related.length > 0 && <><h4>함께 읽을 자료</h4><div className="kl-actions">{detail.related.map(d =>
            <button key={d.id} onClick={() => choose(d.id)} lang="en">{d.title}</button>)}</div></>}
          <details className="kl-provenance"><summary>수집 기록</summary>
            <p>수집 일시 {detail.downloaded} · 버전 {detail.version}</p><p>SHA-256 {detail.sha256}</p>
          </details>
        </>}
      </article>
    </div>
  </section>
}

