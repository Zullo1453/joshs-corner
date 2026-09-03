(() => {
  const number = value => new Intl.NumberFormat(undefined, {maximumFractionDigits: 2}).format(value);
  const date = value => new Intl.DateTimeFormat(undefined, {day:'numeric', month:'short', year:'numeric'}).format(new Date(`${value}T12:00:00`));
  const pace = value => {const seconds=Math.round(value); return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')} /km`;};
  const duration=value=>{const seconds=Math.round(value);return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;};
  const names = {volume:'Session volume', max_weight:'Maximum weight', max_reps:'Best set reps', total_reps:'Total reps', pace:'Average pace · lower is faster', distance:'Distance by run',elapsed:'Completion time · lower is quicker',hold:'Longest hold',total_time:'Session time'};
  function chart(element) {
    const points=JSON.parse(element.dataset.points||'[]'), metric=element.dataset.metric;
    if (!points.length) return;
    const running=['pace','distance','elapsed'].includes(metric), timed=['hold','total_time'].includes(metric);
    const unit=value=>metric==='pace'?pace(value):(timed||metric==='elapsed'?duration(value):`${number(value)} ${metric==='distance'?'km':(['max_reps','total_reps'].includes(metric)?'reps':'kg')}`);
    const width=Math.max(280,element.clientWidth||600), height=250, pad={left:70,right:30,top:22,bottom:42};
    const values=points.map(point=>point[metric]);
    let min=metric==='pace'?Math.min(...values)*.95:0, max=Math.max(...values,1)*1.05;
    const x=index=>points.length===1?(pad.left+width-pad.right)/2:pad.left+index*(width-pad.left-pad.right)/(points.length-1);
    const y=value=>pad.top+(1-(value-min)/(max-min))*(height-pad.top-pad.bottom);
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('role','group');svg.setAttribute('aria-label',names[metric]);
    const node=(tag,attrs,text)=>{const child=document.createElementNS(svg.namespaceURI,tag);Object.entries(attrs).forEach(([key,value])=>child.setAttribute(key,value));if(text!==undefined)child.textContent=text;svg.append(child);return child;};
    for(let i=0;i<3;i++){const value=min+(max-min)*i/2;
      node('path',{d:`M ${pad.left} ${y(value)} H ${width-pad.right}`,stroke:'#4b3c32',fill:'none'});
      node('text',{x:pad.left-8,y:y(value)+4,fill:'#c8ada0','font-size':10,'text-anchor':'end'},unit(value));
    }
    node('polyline',{points:points.map((point,i)=>`${x(i)},${y(point[metric])}`).join(' '),fill:'none',stroke:'#e4a36d','stroke-width':2.5});
    const detail=document.createElement('p');detail.className='gym-chart-detail';detail.setAttribute('aria-live','polite');
    const description=point=>running?`${point.route} · ${number(point.distance)} km · ${point.duration} · ${point.pace_label}`:(timed?`Longest hold: ${duration(point.hold)} · Total time: ${duration(point.total_time)} · ${point.sets.join(' · ')}`:(['max_reps','total_reps'].includes(metric)?`Best set: ${number(point.max_reps)} reps · Total reps: ${number(point.total_reps)} · ${point.sets.join(' · ')}`:`Max weight: ${number(point.max_weight)} kg · Volume: ${number(point.volume)} kg · ${point.sets.join(' · ')}`));
    const show=point=>{const heading=document.createElement('strong');heading.textContent=date(point.date);detail.replaceChildren(heading,document.createTextNode(description(point)));};
    points.forEach((point,i)=>{
      const circle=node('circle',{cx:x(i),cy:y(point[metric]),r:7,fill:'#f5d1b0',stroke:'#8e5938',tabindex:0,role:'button','aria-label':`${date(point.date)}: ${description(point)}`});
      ['mouseenter','focus','click'].forEach(event=>circle.addEventListener(event,()=>show(point)));
      circle.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();show(point);}});
    });
    const shown=Math.min(points.length,width<400?2:4);
    for(let i=0;i<shown;i++){const index=shown===1?0:Math.round(i*(points.length-1)/(shown-1));node('text',{x:x(index),y:height-14,fill:'#c8ada0','font-size':11,'text-anchor':'middle'},date(points[index].date).replace(/ \d{4}$/, ''));}
    element.replaceChildren(svg,detail);show(points.at(-1));
  }
  document.querySelectorAll('.gym-chart').forEach(chart);
})();
