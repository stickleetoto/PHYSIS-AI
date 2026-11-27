import type { Snapshot } from './domain'

export type MathMode = 'function'|'limit'|'derivative'|'integral'
export type Topic = MathMode|'vector'|'trig'|'matrix'|'statistics'|'numerics'|'ode'
export type Point = [number,number]
export interface LabInput {
  mode: MathMode; expression: string; other?: string; indefinite?: boolean; params: Record<'a'|'b'|'c',number>
  lo: number; hi: number; point: number; step: number; lower: number; upper: number; divisions: number
}
export interface Curve {label:string; segments:Point[][]}
export interface LabResult {
  status:string; detail?:string; rows?:{label:string;value:string;latex?:string;kind:'exact'|'numeric'|'note'}[]
  curves?:Curve[]; steps?:string[]; guides?:{vertical?:number[];horizontal?:number[]}
}
export const topics = {
  ode:{name:'미분방정식과 시간 변화',goal:'같은 초기값에서 시간 간격이 궤적 오차에 주는 영향을 확인합니다.',example:'선형 용수철은 위치가 바뀌면 복원력과 가속도도 달라집니다.',law:"y'=ry,\\qquad m x''+b x'+kx=0",meaning:'r은 성장률, m은 질량, b는 감쇠 계수, k는 용수철 상수입니다.',question:'시간 간격을 절반으로 바꾸면 두 적분기의 오차가 어떻게 달라질까요?',limit:'방향장 화살표는 방향을 읽기 위해 정규화했습니다. 크기로 변화율을 비교할 수 없습니다.'},
  matrix:{name:'행렬과 선형변환',goal:'행렬의 열을 바꾸며 기저와 격자의 변화를 비교합니다.',example:'전단변환은 정사각형을 평행사변형으로 바꿀 수 있습니다.',law:'A\\mathbf x=\\mathbf b',meaning:'A는 선형변환, x는 미지 벡터, b는 목표 벡터입니다.',question:'두 열이 평행하면 평면 격자와 역행렬에 어떤 변화가 생길까요?',limit:'고유공간과 격자 그림은 2×2 행렬에서 제공합니다.'},
  statistics:{name:'통계와 실험 데이터',goal:'측정값의 분포와 회귀 잔차를 살펴봅니다.',example:'시간과 위치의 산점도에 직선을 맞추면 잔차로 가속도의 영향을 관찰할 수 있습니다.',law:'\\hat y=mx+b,\\qquad e_i=y_i-\\hat y_i',meaning:'m은 기울기, b는 절편, e는 잔차입니다.',question:'잔차가 일정한 곡선을 그리면 직선 회귀로 충분할까요?',limit:'상관관계만으로 인과관계를 추론할 수 없습니다. 모든 x 또는 y가 같으면 상관계수가 정의되지 않습니다.'},
  numerics:{name:'근 찾기와 수치 근사',goal:'동일한 함수에서 수치해법의 수렴과 오차를 비교합니다.',example:'제곱이 2가 되는 수를 구간을 좁히거나 접선으로 접근해 찾습니다.',law:'x_{n+1}=x_n-f(x_n)/f\'(x_n)',meaning:'n은 반복 번호, xₙ은 현재 근의 추정값입니다.',question:'시작점에서 기울기가 0이면 뉴턴법은 어떻게 될까요?',limit:'허용 오차를 만족한 근사해 하나가 구간 안 모든 근을 뜻하지는 않습니다.'},
  function: {name:'함수와 그래프',goal:'같은 좌표계에서 두 식의 모양과 교점을 비교합니다.',example:'포물선의 꼭짓점을 옮기면 같은 직선과 만나는 점의 개수가 달라집니다.',law:'y=a(x-b)^2+c',meaning:'a는 세로 배율, b와 c는 가로·세로 이동량입니다.',question:'a의 부호만 바꾸면 대칭축과 꼭짓점은 어떻게 되나요?',limit:'정의역에서 빠진 점은 식을 약분해도 돌아오지 않습니다.'},
  limit:{name:'극한과 연속',goal:'한 점으로 다가가는 두 방향과 그 점의 값을 비교합니다.',example:'구멍이 난 직선 위에서도 양쪽의 높이는 같은 값에 다가갈 수 있습니다.',law:'\\lim_{x\\to p^-}f(x),\\quad\\lim_{x\\to p^+}f(x)',meaning:'p는 접근 위치이고 h는 관찰 간격입니다.',question:'좌우 극한이 같으면 그 점에서 항상 연속일까요?',limit:'유한한 표본만으로 극한의 존재를 증명할 수 없습니다.'},
  derivative:{name:'미분과 접선',goal:'할선의 기울기가 순간변화율로 접근하는 과정을 관찰합니다.',example:'자동차 위치의 두 측정 시각을 좁히면 구간 평균속도가 순간속도에 다가갑니다.',law:"f'(p)=\\lim_{h\\to0}\\frac{f(p+h)-f(p)}h",meaning:'p는 접점, h는 두 점 사이의 입력 간격입니다.',question:'가속도가 일정하면 위치의 이계도함수는 어떤 모양일까요?',limit:'뾰족점에서 한쪽 기울기만으로 접선을 정할 수 없습니다.'},
  integral:{name:'적분과 누적',goal:'분할 수를 바꾸며 근삿값과 정적분의 차이를 측정합니다.',example:'시간별 속도를 합산하면 이동한 방향을 반영한 변위를 얻습니다.',law:'F(u)=\\int_l^u f(x)\\,dx,\\quad F\'(u)=f(u)',meaning:'l과 u는 적분 끝점이며, 분할 수는 근사 띠의 개수입니다.',question:'음수 구간이 있을 때 총넓이와 정적분은 어떻게 다른가요?',limit:'기본정리의 미분 관계는 해당 점에서 피적분함수가 연속일 때 적용합니다.'},
  vector:{name:'벡터와 정사영',goal:'두 화살표를 조작해 합성과 방향 성분을 찾습니다.',example:'두 사람이 함께 미는 힘은 각 방향 성분을 더해 구합니다.',law:'\\mathbf u\\cdot\\mathbf v=|\\mathbf u||\\mathbf v|\\cos\\theta',meaning:'내적은 두 벡터가 같은 방향을 향하는 정도를 나타냅니다.',question:'수직인 힘이 이동 방향으로 한 일은 얼마인가요?',limit:'영벡터는 방향과 단위 벡터를 정할 수 없습니다.'},
  trig:{name:'삼각함수와 단위원',goal:'회전하는 점의 좌표와 주기적인 신호를 연결합니다.',example:'원판의 점을 옆에서 보면 한 축의 좌표가 주기적으로 오르내립니다.',law:'y=A\\sin(\\omega t+\\phi)',meaning:'A는 배율, ω는 각진동수, φ는 시작 위상입니다.',question:'각진동수를 두 배로 하면 한 주기 시간은 어떻게 바뀌나요?',limit:'tan은 cos가 0인 각에서 정의되지 않습니다.'},
} satisfies Record<Topic,{name:string;goal:string;example:string;law:string;meaning:string;question:string;limit:string}>
export function initialInput(mode:MathMode):LabInput {
  return {mode,expression:({function:'a*(x-b)^2+c',limit:'(x^2-1)/(x-1)',derivative:'x^3',integral:'x^2-1'})[mode],
    other:mode==='function'?'x+1':undefined,params:{a:1,b:0,c:0},lo:-3,hi:3,point:1,step:0.5,lower:-1,upper:2,divisions:8}
}

export type Triple = [number,number,number]
export function vectors(u:Triple,v:Triple,scale:number) {
  const len=Math.hypot(...u), otherLen=Math.hypot(...v), dot=u.reduce((s,n,i)=>s+n*v[i],0)
  const cross:Triple=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
  const hasDirections=Boolean(len && otherLen)
  return {len,otherLen,dot,cross,unit:len?u.map(n=>n/len):null,add:u.map((n,i)=>n+v[i]),sub:u.map((n,i)=>n-v[i]),
    scaled:u.map(n=>n*scale), projection:otherLen?v.map(n=>dot*n/(otherLen*otherLen)):null,
    angle:hasDirections?Math.atan2(Math.hypot(...cross),dot):null,
    parallel:hasDirections?Math.hypot(...cross)<=1e-12*len*otherLen:null,orthogonal:Math.abs(dot)<=1e-12*len*otherLen}
}
export interface TrigSettings {amplitude:number; omega:number; phase:number; t:number; fn:'sin'|'cos'|'tan'}
export function trigValue(angle:number,fn:TrigSettings['fn']) {
  if(fn==='tan' && Math.abs(Math.cos(angle))<1e-12)return null
  return Math[fn](angle)
}
export function trigPoint(s:TrigSettings,t=s.t):number|null {
  const value=trigValue(s.omega*t+s.phase,s.fn)
  return value===null?null:s.amplitude*value
}
export function trigCurve(s:TrigSettings,start:number,end:number):Curve {
  const segments:Point[][]=[]; let part:Point[]=[]
  let branch:number|undefined
  for(let i=0;i<=240;i++){
    const t=start+(end-start)*i/240, angle=s.omega*t+s.phase, value=trigPoint(s,t)
    const next=Math.floor((angle+Math.PI/2)/Math.PI)
    if(value===null || (s.fn==='tan' && branch!==undefined && branch!==next)){
      if(part.length)segments.push(part)
      part=[]
    }
    if(value!==null)part.push([t,value])
    branch=next
  }
  if(part.length)segments.push(part)
  return {label:s.fn+'(ωt+φ) × A',segments}
}

export const bridges = {
  position:{label:'위치 → 속도·가속도',model:'acceleration',mode:'derivative',expression:'a+b*x+c*x^2/2',params:{a:0,b:2,c:2},units:'x는 시간(s), a는 초기 위치(m), b는 초기 속도(m/s), c는 가속도(m/s²).'},
  displacement:{label:'속도 적분 → 변위',model:'acceleration',mode:'integral',expression:'b+c*x',params:{a:0,b:2,c:2},units:'x는 시간(s), b는 초기 속도(m/s), c는 가속도(m/s²). 적분 결과는 변위(m).'},
  constantWork:{label:'일정한 힘 → 일',model:'newton',mode:'integral',expression:'a',params:{a:3,b:0,c:0},units:'x는 위치(m), a는 수평 힘(N). 두 위치 사이에서 힘이 한 일은 J.'},
  springWork:{label:'복원력 → 일',model:'spring',mode:'integral',expression:'-a*x',params:{a:4,b:0,c:0},units:'x는 평형점으로부터의 변위(m), a는 용수철 상수(N/m). 적분은 탄성력이 한 일(J).'},
} as const
export type BridgeId=keyof typeof bridges
export type MathEntry = {topic:Topic; bridge?:BridgeId; input?:LabInput; trig?:TrigSettings}
export const bridgeInput=(id:BridgeId,snapshot?:Snapshot):LabInput=>{
  const b=bridges[id], p=snapshot?.experiment.values
  const params={...b.params} as LabInput['params']
  if(p && snapshot?.experiment.model===b.model){
    if(b.model==='acceleration')Object.assign(params,{a:p.x0,b:p.v0,c:p.a})
    else params.a=b.model==='newton'?p.force:p.k
  }
  return {...initialInput(b.mode),expression:b.expression,other:undefined,lo:0,hi:4,lower:id==='springWork'?1:0,upper:2,params}
}
export function fromPhysics(snapshot:Snapshot):MathEntry|null {
  const {model,values:p}=snapshot.experiment
  if(model==='free_fall'){
    const end=Math.min(snapshot.experiment.duration,Math.sqrt(2*p.height/p.g))
    return {topic:'derivative',input:{...initialInput('derivative'),expression:'a-b*x^2/2',
      params:{a:p.height,b:p.g,c:0},lo:0,hi:end,point:end/2,step:end/8}}
  }
  if(model==='uniform')return {topic:'derivative',input:{...initialInput('derivative'),expression:'a+b*x',
    params:{a:p.x0,b:p.v0,c:0},lo:0,hi:snapshot.experiment.duration,point:0}}
  if(model==='spring'){
    const omega=Math.sqrt(p.k/p.mass)
    return {topic:'trig',trig:{fn:'cos',amplitude:Math.hypot(p.x0,p.v0/omega),omega,phase:Math.atan2(-p.v0/omega,p.x0),t:0}}
  }
  if(model==='wave_transverse')return {topic:'trig',trig:{fn:'sin',amplitude:p.amplitude,omega:-2*Math.PI*p.frequency,phase:0,t:0}}
  const bridge=model==='acceleration'?'position':model==='newton'?'constantWork':null
  return bridge?{topic:bridges[bridge].mode,bridge,input:bridgeInput(bridge,snapshot)}:null
}
export function physicsValues(id:BridgeId,input:LabInput):Record<string,number>|null {
  const {a,b,c}=input.params
  if(input.expression.trim()!==bridges[id].expression)return null
  if(id==='position')return {x0:a,v0:b,a:c}
  if(id==='displacement')return {x0:a+b*input.lower+c*input.lower**2/2,v0:b+c*input.lower,a:c}
  if(id==='constantWork')return {mass:1,force:a,x0:input.lower,v0:input.upper-input.lower-a/2}
  return {mass:1,k:a,x0:input.lower,v0:Math.sqrt(a)*input.upper}
}
export function bridgeDuration(id:BridgeId,input:LabInput){
  if(id==='displacement')return input.upper-input.lower
  if(id==='constantWork')return 1
  if(id==='springWork')return Math.PI/(2*Math.sqrt(input.params.a))
  return undefined
}
