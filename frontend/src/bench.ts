import type { ChatResult, Snapshot } from './domain'
import type { Lesson } from './learning'

interface TutorResult extends Omit<ChatResult, 'action'> {
  action: ChatResult['action'] | 'compare'
  lesson: Lesson | null
}
type TutorEvent = {event:'stage'; stage:string} | {event:'text'; text:string} |
  {event:'result'; result:TutorResult} | {event:'error'; detail:string}

export interface Board { anchor: string; members: Snapshot[]; analysis: string[] }
export interface Selection { provider: string; model: string }
export interface FocusAction {
  op: string
  index?: number
  quantity?: string
  variable?: string
  time?: number
  start?: number
  end?: number
}

export function sharedQuantities(members: Snapshot[]) {
  if (!members.length) return []
  const first = members[0].experiment.measurements
  return Object.keys(first).filter(q => members.every(s =>
    s.experiment.measurements[q] === first[q] && Boolean(s.run.series['0.' + q])))
}

export async function readTutorStream(body: object, signal: AbortSignal,
  onEvent: (event: TutorEvent) => void) {
  const response = await fetch('/api/tutor/stream', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body), signal})
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || '튜터 요청을 시작하지 못했습니다.')
  }
  if (!response.body) throw new Error('스트림을 열 수 없습니다.')
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let pending = '', complete = false
  try {
    while (!complete) {
      const {value, done} = await reader.read()
      pending += decoder.decode(value, {stream:!done})
      const rows = pending.split('\n')
      pending = rows.pop() || ''
      for (const row of rows) {
        if (!row) continue
        const event: TutorEvent = JSON.parse(row)
        if (event.event === 'error') throw new Error(event.detail)
        onEvent(event)
        if (event.event === 'result') complete = true
      }
      if (done) break
    }
    if (!complete) throw new Error('연결이 끊겼습니다. 실험 기록을 다시 불러와 주세요.')
  } finally { reader.releaseLock() }
}
