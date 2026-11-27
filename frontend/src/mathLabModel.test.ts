import {describe,it,expect} from 'vitest'
import {bridgeDuration,bridgeInput,physicsValues,vectors,trigPoint,trigCurve,trigValue,fromPhysics,type TrigSettings} from './mathLabModel'
import type {Snapshot} from './domain'
const snapshot=(model:string,values:Record<string,number>)=>({experiment:{model,values}} as Snapshot)
describe('geometry measurements and physics bridges',()=>{
  it('uses the right-handed cross product, angle, magnitude and projection',()=>{
    const r=vectors([3,4,0],[0,2,0],3)
    expect(r.len).toBe(5);expect(r.cross).toEqual([0,0,6]);expect(r.dot).toBe(8)
    expect(r.projection).toEqual([0,4,0]);expect(r.unit).toEqual([.6,.8,0]);expect(r.angle).toBeCloseTo(.643501108793)
    expect(vectors([0,0,2],[1,0,0],1).cross).toEqual([0,2,0])
  })
  it('retains undefined direction and projection for zero denominators',()=>{
    const r=vectors([0,0,0],[0,0,0],2)
    expect([r.angle,r.unit,r.projection,r.parallel]).toEqual([null,null,null,null])
  })
  it('keeps tangent branches separate at unsampled poles',()=>{
    const s:TrigSettings={amplitude:1,omega:1,phase:.01,t:0,fn:'tan'}
    const spans=trigCurve(s,0,2*Math.PI).segments
    expect(spans).toHaveLength(3)
    for(const pole of [Math.PI/2-.01,3*Math.PI/2-.01])expect(spans.every(a=>a.at(-1)![0]<pole||a[0][0]>pole)).toBe(true)
    expect(trigValue(90*Math.PI/180,'tan')).toBeNull()
    expect(trigValue(30*Math.PI/180,'sin')).toBeCloseTo(.5)
  })
  it('reconstructs spring phase for nonzero initial velocity and travelling-wave sign',()=>{
    const s=fromPhysics(snapshot('spring',{mass:1,k:4,x0:0,v0:2}))!.trig!
    expect(trigPoint(s,0)).toBeCloseTo(0);expect(trigPoint(s,Math.PI/4)).toBeCloseTo(1)
    const wave=fromPhysics(snapshot('wave_transverse',{amplitude:.02,frequency:1}))!.trig!
    expect(trigPoint(wave,.25)).toBeCloseTo(-.02)
  })
  it('transfers registered coefficients and refuses an edited arbitrary formula',()=>{
    const d=bridgeInput('position',snapshot('acceleration',{x0:3,v0:-2,a:1}))
    expect(physicsValues('position',d)).toEqual({x0:3,v0:-2,a:1})
    expect(physicsValues('position',{...d,expression:'x^3'})).toBeNull()
  })
  it('starts the physical trajectory at a nonzero integration time',()=>{
    const d={...bridgeInput('displacement'),lower:1,upper:3,params:{a:1,b:2,c:2}}
    expect(physicsValues('displacement',d)).toEqual({x0:4,v0:4,a:2})
    expect(bridgeDuration('displacement',d)).toBe(2)
    const spring=bridgeInput('springWork')
    expect(physicsValues('springWork',spring)).toEqual({mass:1,k:4,x0:1,v0:4})
    expect(bridgeDuration('springWork',spring)).toBeCloseTo(Math.PI/4)
  })
})
