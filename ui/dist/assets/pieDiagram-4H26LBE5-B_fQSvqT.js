import{t as e}from"./arc-DxZaIiTO.js";import{i as t,p as n}from"./chunk-5ZQYHXKU-CzajrFqz.js";import{i as r,r as i}from"./src-8GYos7co.js";import{I as a,gt as o,ht as s,tt as c}from"./index-B0VH3zWX.js";import{t as l}from"./mermaid-parser.core-D--_8rvt.js";import{H as u,K as d,U as f,a as p,c as m,f as h,v as g,w as _,x as v,y}from"./chunk-CSCIHK7Q-VWk3yB0Q.js";import{t as b}from"./chunk-WU5MYG2G-Bk3gMv_y.js";import{t as x}from"./chunk-4BX2VUAB-BEyGp8ah.js";function S(e,t){return t<e?-1:t>e?1:t>=e?0:NaN}function C(e){return e}function w(){var e=C,t=S,n=null,r=o(0),i=o(s),a=o(0);function l(o){var l,u=(o=c(o)).length,d,f,p=0,m=Array(u),h=Array(u),g=+r.apply(this,arguments),_=Math.min(s,Math.max(-s,i.apply(this,arguments)-g)),v,y=Math.min(Math.abs(_)/u,a.apply(this,arguments)),b=y*(_<0?-1:1),x;for(l=0;l<u;++l)(x=h[m[l]=l]=+e(o[l],l,o))>0&&(p+=x);for(t==null?n!=null&&m.sort(function(e,t){return n(o[e],o[t])}):m.sort(function(e,n){return t(h[e],h[n])}),l=0,f=p?(_-u*b)/p:0;l<u;++l,g=v)d=m[l],x=h[d],v=g+(x>0?x*f:0)+b,h[d]={data:o[d],index:l,value:x,startAngle:g,endAngle:v,padAngle:y};return h}return l.value=function(t){return arguments.length?(e=typeof t==`function`?t:o(+t),l):e},l.sortValues=function(e){return arguments.length?(t=e,n=null,l):t},l.sort=function(e){return arguments.length?(n=e,t=null,l):n},l.startAngle=function(e){return arguments.length?(r=typeof e==`function`?e:o(+e),l):r},l.endAngle=function(e){return arguments.length?(i=typeof e==`function`?e:o(+e),l):i},l.padAngle=function(e){return arguments.length?(a=typeof e==`function`?e:o(+e),l):a},l}var T=h.pie,E={sections:new Map,showData:!1,config:T},D=E.sections,O=E.showData,k=structuredClone(T),A={getConfig:i(()=>structuredClone(k),`getConfig`),clear:i(()=>{D=new Map,O=E.showData,p()},`clear`),setDiagramTitle:d,getDiagramTitle:_,setAccTitle:f,getAccTitle:y,setAccDescription:u,getAccDescription:g,addSection:i(({label:e,value:t})=>{if(t<0)throw Error(`"${e}" has invalid value: ${t}. Negative values are not allowed in pie charts. All slice values must be >= 0.`);D.has(e)||(D.set(e,t),r.debug(`added new section: ${e}, with value: ${t}`))},`addSection`),getSections:i(()=>D,`getSections`),setShowData:i(e=>{O=e},`setShowData`),getShowData:i(()=>O,`getShowData`)},j=i((e,t)=>{x(e,t),t.setShowData(e.showData),e.sections.map(t.addSection)},`populateDb`),M={parse:i(async e=>{let t=await l(`pie`,e);r.debug(t),j(t,A)},`parse`)},N=i(e=>`
  .pieCircle{
    stroke: ${e.pieStrokeColor};
    stroke-width : ${e.pieStrokeWidth};
    opacity : ${e.pieOpacity};
  }
  .pieOuterCircle{
    stroke: ${e.pieOuterStrokeColor};
    stroke-width: ${e.pieOuterStrokeWidth};
    fill: none;
  }
  .pieTitleText {
    text-anchor: middle;
    font-size: ${e.pieTitleTextSize};
    fill: ${e.pieTitleTextColor};
    font-family: ${e.fontFamily};
  }
  .slice {
    font-family: ${e.fontFamily};
    fill: ${e.pieSectionTextColor};
    font-size:${e.pieSectionTextSize};
    // fill: white;
  }
  .legend text {
    fill: ${e.pieLegendTextColor};
    font-family: ${e.fontFamily};
    font-size: ${e.pieLegendTextSize};
  }
`,`getStyles`),P=i(e=>{let t=[...e.values()].reduce((e,t)=>e+t,0),n=[...e.entries()].map(([e,t])=>({label:e,value:t})).filter(e=>e.value/t*100>=1);return w().value(e=>e.value).sort(null)(n)},`createPieArcs`),F={parser:M,db:A,renderer:{draw:i((i,o,s,c)=>{r.debug(`rendering pie chart
`+i);let l=c.db,u=v(),d=t(l.getConfig(),u.pie),f=b(o),p=f.append(`g`);p.attr(`transform`,`translate(225,225)`);let{themeVariables:h}=u,[g]=n(h.pieOuterStrokeWidth);g??=2;let _=d.textPosition,y=e().innerRadius(0).outerRadius(185),x=e().innerRadius(185*_).outerRadius(185*_);p.append(`circle`).attr(`cx`,0).attr(`cy`,0).attr(`r`,185+g/2).attr(`class`,`pieOuterCircle`);let S=l.getSections(),C=P(S),w=[h.pie1,h.pie2,h.pie3,h.pie4,h.pie5,h.pie6,h.pie7,h.pie8,h.pie9,h.pie10,h.pie11,h.pie12],T=0;S.forEach(e=>{T+=e});let E=C.filter(e=>(e.data.value/T*100).toFixed(0)!==`0`),D=a(w).domain([...S.keys()]);p.selectAll(`mySlices`).data(E).enter().append(`path`).attr(`d`,y).attr(`fill`,e=>D(e.data.label)).attr(`class`,`pieCircle`),p.selectAll(`mySlices`).data(E).enter().append(`text`).text(e=>(e.data.value/T*100).toFixed(0)+`%`).attr(`transform`,e=>`translate(`+x.centroid(e)+`)`).style(`text-anchor`,`middle`).attr(`class`,`slice`);let O=p.append(`text`).text(l.getDiagramTitle()).attr(`x`,0).attr(`y`,-400/2).attr(`class`,`pieTitleText`),k=[...S.entries()].map(([e,t])=>({label:e,value:t})),A=p.selectAll(`.legend`).data(k).enter().append(`g`).attr(`class`,`legend`).attr(`transform`,(e,t)=>{let n=22*k.length/2;return`translate(216,`+(t*22-n)+`)`});A.append(`rect`).attr(`width`,18).attr(`height`,18).style(`fill`,e=>D(e.label)).style(`stroke`,e=>D(e.label)),A.append(`text`).attr(`x`,22).attr(`y`,14).text(e=>l.getShowData()?`${e.label} [${e.value}]`:e.label);let j=512+Math.max(...A.selectAll(`text`).nodes().map(e=>e?.getBoundingClientRect().width??0)),M=O.node()?.getBoundingClientRect().width??0,N=450/2-M/2,F=450/2+M/2,I=Math.min(0,N),L=Math.max(j,F)-I;f.attr(`viewBox`,`${I} 0 ${L} 450`),m(f,450,L,d.useMaxWidth)},`draw`)},styles:N};export{F as diagram};