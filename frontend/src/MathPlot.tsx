import { useId, useRef, useState } from 'react'
import { numberText, range } from './domain'
import { downloadMathGraph } from './pngExport'
import type { Curve, LabResult, Point } from './mathLabModel'

const inks=['#c3ef88','#89d5ed','#f2ae84','#c2adf7','#ffda75','#ffacc7']
export function MathPlot({curves,window:extent,title,guides,marker}:{curves:Curve[];window:[number,number];title:string;guides?:LabResult['guides'];marker?:Point}) {
  const svg=useRef<SVGSVGElement>(null), clip=useId(), [error,setError]=useState('')
  const points=curves.flatMap(c=>c.segments.flat()).filter(([x])=>x>=extent[0] && x<=extent[1])
  const [ymin,ymax]=range(points.map(p=>p[1]).concat(marker?[marker[1]]:[]),true)
  const px=(x:number)=>48+542*(x-extent[0])/(extent[1]-extent[0]),py=(y:number)=>263-212*(y-ymin)/(ymax-ymin)
  function downloadData(){
    const rows=[['curve','segment','x','y'],...curves.flatMap(c=>c.segments.flatMap((s,i)=>s.map(([x,y])=>[c.label,i,x,y])))]
    const quote=(x:string|number)=>'"'+String(x).replaceAll('"','""')+'"'
    const url=URL.createObjectURL(new Blob(['\ufeff'+rows.map(r=>r.map(quote).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}))
    const a=document.createElement('a');a.href=url;a.download='physis-math-graph.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  return <figure className="ml-chart"><figcaption>{title}</figcaption>
    <svg ref={svg} viewBox="0 0 620 316" aria-label={title} role="img">
      <rect width="620" height="316" fill="#152127"/>
      <text x="48" y="26" fill="#dce8eb" fontSize="13">{title.slice(0,75)}</text>
      <defs><clipPath id={clip}><rect x="47" y="49" width="545" height="216"/></clipPath></defs>
      {[0,0.25,.5,.75,1].map(n=><g key={n} stroke="#364950">
        <path d={'M48 '+(263-n*212)+'H590 M'+(48+n*542)+' 51V263'} strokeDasharray="3 5"/>
        <g fill="#b2c3c8" stroke="none" fontSize="10"><text x="44" y={266-n*212} textAnchor="end">{numberText(ymin+n*(ymax-ymin),2)}</text>
        <text x={48+n*542} y="284" textAnchor="middle">{numberText(extent[0]+n*(extent[1]-extent[0]),2)}</text></g></g>)}
      <g clipPath={'url(#'+clip+')'}>
        <path d={'M48 '+py(0)+'H590 M'+px(0)+' 51V263'} stroke="#82949b"/>
        {guides?.vertical?.map((x,i)=><path key={'v'+i} d={'M'+px(x)+' 51V263'} stroke="#f69b79" strokeDasharray="5 3"/>)}
        {guides?.horizontal?.map((y,i)=><path key={'h'+i} d={'M48 '+py(y)+'H590'} stroke="#f69b79" strokeDasharray="5 3"/>)}
        {curves.map((c,i)=><g key={i} data-curve={c.label}>{c.segments.map((s,j)=>s.length===1?
          <circle key={j} cx={px(s[0][0])} cy={py(s[0][1])} r="3" fill={inks[i%inks.length]}/>:
          <polyline key={j} points={s.map(([x,y])=>px(x)+','+py(y)).join(' ')} fill="none" stroke={inks[i%inks.length]} strokeWidth="2"/>)}</g>)}
        {marker&&<circle cx={px(marker[0])} cy={py(marker[1])} r="5" fill="#ffdd87" stroke="#102025"/>}
      </g>
    </svg>
    <div className="ml-legend">{curves.map((c,i)=><span key={i} style={{color:inks[i%inks.length]}}>{c.label}</span>)}</div>
    <div className="ml-actions"><button onClick={()=>{if(svg.current)void downloadMathGraph(svg.current).catch(e=>setError(String(e)))}}>그래프 PNG</button>
    <button onClick={downloadData}>계산 데이터 CSV</button></div>{error&&<p role="alert">{error}</p>}</figure>
}
