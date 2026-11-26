import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { FieldScene } from './FieldScene'
import type { Snapshot } from './domain'

describe('field emphasis',()=>{
  it('outlines only the requested pressure station using its actual measurement',()=>{
    const snapshot: Snapshot = {
      revision:1, explanation:'',
      experiment:{
        id:'fixture', model:'bernoulli', title:'베르누이', category:'유체', goal:'정압을 비교합니다.',
        formula:'p+ρv²/2', assumptions:['정상 유동'], variables:[], methods:['analytic'], method:'analytic',
        measurements:{pressure:'Pa',speed:'m/s'}, visualization:'bernoulli', comparison:'두 단면',
        dt:.02, duration:4, values:{area_in:.04,area_out:.02}, objects:['입구','출구'],
      },
      run:{
        status:'VERIFIED', facts:{}, checks:[], convergence:[], times:[0],
        series:{'0.pressure':[101325],'1.pressure':[99825],'0.speed':[1],'1.speed':[2]},
      },
    }
    const html = renderToStaticMarkup(<FieldScene snapshot={snapshot} index={0} focus={[{op:'highlight_object',index:1}]}/>)
    expect(html).toContain('출구 강조')
    expect(html).not.toContain('입구 강조')
    expect(html).toContain('99.825 kPa')
  })
})
