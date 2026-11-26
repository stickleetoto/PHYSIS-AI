import { useEffect, useRef, useState } from 'react'
import { Settings2, X } from 'lucide-react'
import './provider-settings.css'

export type ProviderSelection = { provider: string; model: string }
type Props = {
  selection: ProviderSelection | null
  onSelect: (value: ProviderSelection) => void
  onClose: () => void
}
type Provider = { id: string; configured: boolean; default_model: string }
type Settings = { default_provider: string | null; providers: Provider[] }
type Diagnostics = { models?: string[]; partial: boolean; count: number; latency_ms: number }
type Usage = {
  provider: string; model: string; latency_ms: number; outcome: string
  requests: { operation: string; input_tokens: number | null; output_tokens: number | null; latency_ms: number }[]
}

const names: Record<string, string> = {
  mock: 'Mock · 로컬 규칙', openai: 'OpenAI', anthropic: 'Anthropic',
  ollama: 'Ollama', compatible: 'OpenAI 호환 API',
}
const hints: Record<string, string> = {
  mock: '인터넷 연결 없이 이 기기에서 질문을 해석합니다.',
  openai: '서버의 OPENAI_API_KEY를 사용합니다.',
  anthropic: '서버의 ANTHROPIC_API_KEY를 사용합니다.',
  ollama: '서버의 OLLAMA_BASE_URL에 설치된 모델을 사용합니다.',
  compatible: '서버의 PHYSIS_COMPATIBLE_BASE_URL과 선택적 API 키를 사용합니다.',
}
const outcomes: Record<string, string> = {
  ok: '완료', success: '완료', completed: '완료', cancelled: '취소', error: '오류', unsupported: '지원 범위 밖',
}

async function localApi<T>(url: string, signal: AbortSignal, method = 'GET'): Promise<T> {
  const response = await fetch(url, { method, signal, cache: 'no-store' })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(typeof error.detail === 'string' ? error.detail : '서버 응답을 확인할 수 없습니다.')
  }
  return response.json()
}

export function ProviderSettings({ selection, onSelect, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const pending = useRef<AbortController | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [provider, setProvider] = useState(selection?.provider || 'mock')
  const [model, setModel] = useState(selection?.model || '')
  const [models, setModels] = useState<string[]>([])
  const [history, setHistory] = useState<Usage[]>([])
  const [historyFailed, setHistoryFailed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const selected = settings?.providers.find(p => p.id === provider)
  const latest = history.find(row => row.provider === provider && row.model === model)
  const validId = /^[A-Za-z0-9][A-Za-z0-9._+@:/-]{0,199}$/.test(model)

  useEffect(() => {
    const node = dialog.current
    node?.showModal()
    return () => { node?.close(); pending.current?.abort() }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    localApi<Settings>('/api/providers', controller.signal).then(data => {
      const initial = data.providers.find(p => p.id === (selection?.provider ?? data.default_provider))
        ?? data.providers.find(p => p.id === 'mock')
      if (initial && !controller.signal.aborted) {
        setSettings(data)
        setProvider(initial.id)
        setModel(selection?.provider === initial.id ? selection.model : initial.default_model)
      }
    }).catch(err => { if (!controller.signal.aborted) setError(err.message) })
    localApi<{ items: Usage[] }>('/api/usage', controller.signal).then(data => {
      if (!controller.signal.aborted) setHistory(data.items)
    }).catch(() => { if (!controller.signal.aborted) setHistoryFailed(true) })
    return () => controller.abort()
  }, [selection?.provider, selection?.model])

  function changeProvider(id: string) {
    pending.current?.abort()
    setBusy(false); setError(''); setNotice(''); setModels([])
    setProvider(id)
    setModel(selection?.provider === id ? selection.model : settings?.providers.find(p => p.id === id)?.default_model || '')
  }
  async function check(kind: 'probe' | 'models') {
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    setBusy(true); setError(''); setNotice('')
    try {
      const data = await localApi<Diagnostics>(`/api/providers/${provider}/${kind}`, controller.signal, kind === 'probe' ? 'POST' : 'GET')
      if (controller.signal.aborted) return
      if (kind === 'models') setModels(data.models || [])
      const timing = `${data.latency_ms.toLocaleString()} ms`
      setNotice(provider === 'mock' ? '로컬 해석기를 사용할 수 있습니다.' : kind === 'probe'
        ? `모델 목록 서버가 ${timing} 만에 응답했습니다.`
        : `모델 ${data.count}개를 받았습니다.${data.partial ? ' 첫 페이지의 목록입니다.' : ''} 목록에서 선택하거나 ID를 입력하세요.`)
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : '요청을 완료하지 못했습니다.')
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return <dialog ref={dialog} className="provider-dialog" aria-labelledby="provider-title"
    onCancel={event => { event.preventDefault(); onClose() }}>
    <form onSubmit={event => {
      event.preventDefault()
      if (selected?.configured && validId) { onSelect({ provider, model }); onClose() }
    }}>
      <header className="provider-dialog-head">
        <Settings2 size={21} aria-hidden="true" />
        <h2 id="provider-title">AI 공급자 설정</h2>
        <button type="button" aria-label="설정 닫기" onClick={onClose}><X size={18} /></button>
      </header>
      <div className="provider-dialog-body">
        <label className="provider-field">공급자
          <select value={provider} onChange={e => changeProvider(e.target.value)} disabled={!settings}>
            {(settings?.providers || []).map(p => <option key={p.id} value={p.id}>{names[p.id] || p.id}</option>)}
          </select>
        </label>
        {selected && <div className="provider-setup"><span>{selected.configured ? '서버 설정 확인' : '서버 설정 필요'}</span>
          <p>{hints[provider]}</p>{provider !== 'mock' && <p>질문을 보내면 선택한 서버가 질문, 실험 조건·실행 식별자·계산값, 관련 공식과 공개 문헌의 발췌문을 받습니다.</p>}</div>}
        <div className="provider-checks">
          <button type="button" onClick={() => check('probe')} disabled={busy || !selected?.configured}>연결 확인</button>
          <button type="button" onClick={() => check('models')} disabled={busy || !selected?.configured}>모델 목록 조회</button>
        </div>
        <p className="provider-feedback" role="status">{busy ? '확인 중…' : notice}</p>
        {models.length > 0 && <label className="provider-field">조회한 모델
          <select value={models.includes(model) ? model : ''} onChange={e => setModel(e.target.value)}>
            <option value="" disabled>모델 선택</option>
            {models.map(id => <option value={id} key={id}>{id}</option>)}
          </select>
        </label>}
        <label className="provider-field">모델 ID
          <input value={model} disabled={!selected || provider === 'mock'} maxLength={200}
            placeholder="사용할 모델 ID 직접 입력" spellCheck={false} autoComplete="off"
            onChange={e => setModel(e.target.value.trim())} />
        </label>
        {model && !validId && <p className="provider-failure">모델 ID에는 영문, 숫자 및 . _ + @ : / - 기호를 사용할 수 있습니다.</p>}
        {provider !== 'mock' && <p className="provider-help">연결 확인은 모델 목록만 조회합니다. 질문을 보내면 선택한 공급자의 요금이 적용될 수 있습니다.</p>}
        <section className="provider-history" aria-label="사용 기록">
          <h3>최근 사용 기록</h3>
          {latest ? <>
            <p>{outcomes[latest.outcome] || latest.outcome} · {(latest.latency_ms / 1000).toFixed(2)}초 · 모델 요청 {latest.requests.length}회</p>
            {latest.requests.map((req, index) => <p key={index}>{req.operation === 'plan' ? '질문 해석' : '결과 해설'}
              {' · '}입력 {req.input_tokens ?? '미제공'} / 출력 {req.output_tokens ?? '미제공'} 토큰</p>)}
          </> : <p>{historyFailed ? '사용 기록을 불러올 수 없습니다.' : '최근 기록에 이 모델의 요청이 없습니다.'}</p>}
        </section>
        {error && <p role="alert" className="provider-failure">{error}</p>}
      </div>
      <footer><button type="button" onClick={onClose}>닫기</button>
        <button className="provider-apply" disabled={!selected?.configured || !validId || busy}>선택 적용</button>
      </footer>
    </form>
  </dialog>
}

export default ProviderSettings
