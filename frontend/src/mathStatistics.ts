import type {Point} from './mathLabModel'

export const maxDataRows=5000
export function parseData(text:string):Point[]{
  const lines=text.trim().replace(/^\uFEFF/,'').split(/\r?\n/)
  if(lines.length>maxDataRows+1)throw new Error('최대 5,000개의 관측쌍을 지원합니다.')
  const numeric=/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i
  const cells=(s:string)=>s.split(',').map(c=>c.trim().replace(/^"([^"]*)"$/,'$1'))
  const first=cells(lines[0])
  if(first.length===2 && first.every(s=>s && /[a-z가-힣]/i.test(s) && !numeric.test(s)))lines.shift()
  if(!lines.length||lines.length>maxDataRows)throw new Error('1~5,000개의 x,y 관측쌍을 입력하세요.')
  return lines.map((line,i)=>{
    const pair=cells(line)
    if(pair.length!==2||pair.some(t=>!numeric.test(t)||!Number.isFinite(Number(t))||Math.abs(Number(t))>1e12))
      throw new Error((i+1)+'번째 관측쌍에 빈 값 또는 지원 범위 밖의 값이 있습니다.')
    return [Number(pair[0]),Number(pair[1])]
  })
}
export function statistics(data:Point[]){
  if(!data.length)throw new Error('관측값이 필요합니다.')
  const n=data.length
  const ys=data.map(p=>p[1]).sort((a,b)=>a-b)
  const mean=(values:number[])=>values[0]+values.reduce((sum,x)=>sum+(x-values[0])/values.length,0)
  const mx=mean(data.map(p=>p[0])), my=mean(ys)
  const sum=(f:(x:number,y:number)=>number)=>data.reduce((total,[x,y])=>total+f(x,y),0)
  const xx=sum(x=>(x-mx)**2),yy=sum((_,y)=>(y-my)**2),xy=sum((x,y)=>(x-mx)*(y-my))
  const slope=xx>0?xy/xx:null,intercept=slope===null?null:my-slope*mx
  const residuals:Point[]=slope===null?[]:data.map(([x,y])=>[x,(y-my)-slope*(x-mx)])
  const ssr=residuals.reduce((s,[,r])=>s+r*r,0)
  const counts=new Map<number,number>();for(const y of ys)counts.set(y,(counts.get(y)??0)+1)
  const peak=Math.max(...counts.values()),modes=peak===1&&n>1?[]:[...counts].filter(([,c])=>c===peak).map(([v])=>v)
  const low=ys[0],high=ys[n-1],bins=low===high?1:Math.min(16,Math.ceil(Math.sqrt(n)))
  const hist=Array.from({length:bins},(_,i)=>({lo:low+(high-low)*i/bins,hi:low+(high-low)*(i+1)/bins,n:0}))
  for(const y of ys)hist[bins===1?0:Math.min(bins-1,Math.floor((y-low)/(high-low)*bins))].n++
  return {n,mean:my,median:(ys[Math.floor((n-1)/2)]+ys[Math.floor(n/2)])/2,modes,variance:yy/n,
    sample:n>1?yy/(n-1):null,correlation:xx&&yy?xy/Math.sqrt(xx*yy):null,
    slope,intercept,residuals,r2:yy>0&&slope!==null?1-ssr/yy:null,hist,mx}
}
