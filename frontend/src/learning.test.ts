import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { type Snapshot } from './domain'
import { addEvidence, clearLearning, getLearning, latestJudgments, learningArchive, recallLearning, recordExperiment, recordTurn, type Lesson } from './learning'

const s={revision:1,experiment:{id:'e1',model:'free_fall',title:'자유낙하',values:{height:5},dt:.02,duration:4,method:'analytic'},
  run:{status:'VERIFIED',facts:{arrival_time:1}},explanation:'계산 결과 1 s'} as unknown as Snapshot
const discovery:Lesson={mode:'discovery',title:'예측',text:'어떤 변화가 보일까요?',prompt:'가설 작성',actions:[{op:'pause'}]}
const database={experiments:[{id:'e1'}],workbenches:[],usage:[{provider:'mock'}]}
let disk:Map<string,string>
beforeEach(()=>{
  disk=new Map()
  vi.stubGlobal('localStorage',{getItem:(key:string)=>disk.get(key)??null,setItem:(key:string,v:string)=>disk.set(key,v),removeItem:(key:string)=>disk.delete(key)})
  clearLearning()
})
afterEach(()=>vi.unstubAllGlobals())

describe('evidence and local data controls',()=>{
  it('requires direct evidence and preserves a prediction across a revision',()=>{
    recordExperiment(s,'school')
    recordTurn('예상해 볼래',discovery,s,'school',s.explanation)
    expect(getLearning().events.filter(e=>e.kind==='experiment')).toHaveLength(1)
    expect(JSON.stringify(getLearning())).not.toContain(s.explanation)
    expect(latestJudgments(getLearning().events).size).toBe(0)
    addEvidence(s,'school','hypothesis','같은 시각에 닿을 것 같다')
    const prediction=getLearning().events.at(-1)!
    const changed={...s,revision:2}
    addEvidence(changed,'school','observation','두 높이가 같은 시각에 0 m였다',{parent:prediction.id})
    addEvidence(changed,'school','answer','어느 공이 먼저 닿나요?',{verdict:'review',chosen:'무거운 공'})
    expect(latestJudgments(getLearning().events).get('free_fall')?.verdict).toBe('review')
    addEvidence(changed,'school','self','설명할 수 있어요',{verdict:'understood'})
    expect(latestJudgments(getLearning().events).get('free_fall')?.kind).toBe('self')
    const saved=JSON.parse(disk.get('physis.learning.v2')!)
    expect(saved.events.find((e:{kind:string})=>e.kind==='observation')).toMatchObject({parent:prediction.id,revision:2})
  })
  it('exports server and legacy history alongside v2 records, without provider settings',async()=>{
    addEvidence(s,'intro','bookmark','북마크')
    disk.set('physis-history','[{"id":"old"}]')
    disk.set('physis-messages','{"old":["question"]}')
    disk.set('physis-provider','{"secret":"private"}')
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify(database))))
    const archive=await learningArchive()
    expect(archive.server).toEqual(database)
    expect(archive.legacy.history).toEqual([{id:'old'}])
    expect(archive.events.some(e=>e.kind==='bookmark')).toBe(true)
    expect(JSON.stringify(archive)).not.toContain('private')
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')))
    await expect(learningArchive()).rejects.toThrow('offline')
  })
  it('erases persisted and currently displayed v2 data',()=>{
    addEvidence(s,'school','note','지울 메모')
    clearLearning()
    expect(getLearning()).toEqual({version:2,current:null,events:[]})
    expect(disk.has('physis.learning.v2')).toBe(false)
  })
  it('recalls only explicitly entered notes for this experiment and keeps ordinary physics questions in the tutor',()=>{
    expect(recallLearning('내가 아까 세운 가설이 뭐였지?',s,'discovery')?.text).toContain('아직 없습니다')
    addEvidence(s,'school','hypothesis','A와 B의 도착 시각이 같을 것 같다.')
    addEvidence({...s,experiment:{...s.experiment,id:'another'}},'school','hypothesis','다른 실험의 예상')
    const current={...s,revision:2}
    const lesson=recallLearning('내가 아까 세운 가설이 뭐였지?',current,'discovery')!
    expect(lesson.text).toContain('v1')
    expect(lesson.text).toContain('A와 B의 도착 시각이 같을 것 같다.')
    expect(lesson.text).not.toContain('다른 실험')
    expect(recallLearning('왜 무거운 물체가 먼저 떨어진다는 가설은 틀릴까?',s,'explain')).toBeNull()
    recordTurn('높이가 왜 중요해?',null,s,'school','측정값')
    recordTurn('내 가설을 보여줘',lesson,current,'school')
    expect(recallLearning('내 최근 질문을 알려 줘',current,'explain')?.text).toContain('높이가 왜 중요해?')
    expect(recallLearning('내 최근 질문을 알려 줘',current,'explain')?.text).not.toContain('내 가설을 보여줘')
    expect(latestJudgments(getLearning().events).size).toBe(0)
  })
})
