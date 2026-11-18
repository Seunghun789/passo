'use client';
import {useEffect,useState,type ReactNode} from 'react';

// 처음 쓰는 사람: 기록이 없을 때 메뉴마다 채워졌을 때의 모양을 흐린 빈 틀로 보이고(예시 값은 쓰지 않는다),
// 처음 한 바퀴(① 종이 → ② 확인 → ③ 내 기록 → ④ 묻기) 동안 화면 위에 띠를 보인다(PRD 수용 기준 42~44).
const STEPS:[string,string][]=[['① 종이','upload'],['② 확인','review'],['③ 내 기록','home'],['④ 묻기','ask']];
const PART:Record<string,[number,string]>={upload:[0,''],review:[1,'칸'],entities:[1,'대상'],graph:[1,'관계'],records:[2,'기록'],dashboard:[2,'지표'],automation:[2,'챙길 일'],ask:[3,'']};
const NOTE:Record<string,[string,string]>={
 home:['오늘 먼저 볼 것','챙길 일을 켜 두면 걸린 대상이 여기에 먼저 보여요.'],
 review:['확인','AI가 반영한 것 중 사람이 봐야 할 값만 원본과 나란히 물어요.'],
 entities:['대상','AI가 같은 품목·설비·고객을 하나로 묶고, 분류와 정보를 정리해요.'],
 graph:['지식그래프','칸과 대상이 어떻게 이어지는지(기준, 의존 등)를 그림으로 확인해요.'],
 records:['기록','읽은 종이의 줄이 기록으로 쌓여 표로 보여요.'],
 dashboard:['대시보드','쌓인 기록의 숫자 칸 추이와 지표가 여기에 그려져요.'],
 automation:['자동화','기록에서 찾은 기준으로 챙길 일을 켜 두면 홈에 먼저 보여요.'],
 ask:['묻기','쌓인 기록에 물으면, 기록에서 센 답과 근거 기록·원본 사진이 함께 와요.'],
};
export const EMPTY_VIEWS=Object.keys(NOTE);

export function StepTrail({view}:{view:string}){
 const p=PART[view];if(!p)return null;
 return <p className="step-trail" aria-label="네 단계 중 지금">{STEPS.map(([s],i)=><span key={s}>{i>0&&<i aria-hidden="true">→</i>}<span className={i===p[0]?'on':''}>{s}{i===p[0]&&p[1]?` · ${p[1]}`:''}</span></span>)}</p>;
}

const Sk=({w,h}:{w:string,h?:number})=><div className="sk" style={{width:w,height:h}}/>;
const bars=(...ws:string[])=>ws.map((w,i)=><Sk key={i} w={w}/>);
const Line=()=><svg viewBox="0 0 600 120" width="100%" height="120" aria-hidden="true"><polyline fill="none" stroke="#E4E4E7" strokeWidth="3" points="0,100 90,80 180,88 270,50 360,64 450,30 600,40"/></svg>;

export function EmptyState({view,go}:{view:string,go:(v:string)=>void}){
 const [title,note]=NOTE[view]||['',''];
 const upload=<div className="empty-foot"><button className="primary" onClick={()=>go('upload')}>사진 올리기</button><small className="muted">종이 한 장이면 이 화면이 채워져요.</small></div>;
 let ghost:ReactNode=null;
 if(view==='home')ghost=<><div className="ghost-cols">{[0,1,2].map(i=><div className="ghost" key={i}>{i===2&&<p className="ghost-cap">확인</p>}<Sk w="60%" h={14}/><Sk w="30%" h={14}/><Sk w="90%" h={14}/></div>)}</div>
  <p className="ghost-cap">켜 둔 자동화에 걸린 대상과 마지막 기록 날짜가 이 카드에 와요.</p><h2 className="ghost-h">쌓인 기록</h2><div className="ghost"><Line/></div></>;
 if(view==='review')return <><StepTrail view={view}/><h1>{title}</h1><p className="muted">{note}</p>
  <div className="ghost-two"><div className="ghost ghost-call"><b>확인할 종이가 아직 없어요</b><button className="primary" onClick={()=>go('upload')}>사진 올리기</button></div>
   <div><div className="ghost"><p className="ghost-cap">새 기록 종류</p>{bars('60%','100%','100%','100%','100%')}</div><div className="ghost"><p className="ghost-cap">읽기 애매한 칸</p>{bars('80%','50%')}</div></div></div></>;
 if(view==='entities')ghost=<div className="ghost-side"><div className="ghost"><p className="ghost-cap">분류</p>{bars('70%','50%','50%','70%')}</div><div className="ghost"><p className="ghost-cap">대상 표</p>{bars(...Array(7).fill('100%'))}</div></div>;
 if(view==='graph')ghost=<div className="ghost-side wide"><div className="ghost"><svg viewBox="0 0 600 300" width="100%" height="260" stroke="#E4E4E7" strokeWidth="2" fill="#F4F4F5" aria-hidden="true">
   <path d="M200 120 L320 70 L380 200 L240 250 Z M320 70 L460 120 L380 200" fill="none"/><circle cx="200" cy="120" r="22"/><circle cx="380" cy="200" r="22"/><circle cx="320" cy="70" r="12"/><circle cx="240" cy="250" r="12"/><circle cx="460" cy="120" r="12"/></svg></div>
  <div className="ghost"><p className="ghost-cap">점을 누르면 열리는 설정</p>{bars('100%','70%','100%','50%')}</div></div>;
 if(view==='records')ghost=<div className="ghost">{bars(...Array(8).fill('100%'))}</div>;
 if(view==='dashboard')ghost=<><div className="ghost-cols">{[0,1,2].map(i=><div className="ghost" key={i}><Sk w="50%" h={14}/><Sk w="30%" h={14}/><Sk w="40%" h={14}/></div>)}</div><div className="ghost"><Line/></div></>;
 if(view==='automation')ghost=<><div className="ghost"><p className="ghost-cap" style={{margin:0}}>챙길 일을 말로 적어요</p></div>{[0,1,2].map(i=><div className="ghost" key={i}>{bars('40%','70%')}</div>)}</>;
 if(view==='ask')ghost=<><div className="ghost"><p className="ghost-cap">이렇게 찾았어요</p>{bars('100%','75%','50%')}</div><p className="ghost-cap">근거 기록 N줄</p>{bars('100%','100%','100%')}</>;
 return <><StepTrail view={view}/><h1>{title}</h1><p className="muted">{note}</p>{ghost}{upload}</>;
}

// 올리기의 네 칸: ① 칸에 실제 올리기 칸, ②~④는 흐린 빈 틀
export function FourSteps({children}:{children:ReactNode}){
 const cards:[string,string][]=[['② 확인','AI가 정리하고, 틀리면 위험한 값만 물어요'],['③ 내 기록','표 · 지표 · 챙길 일로 쌓여요'],['④ 묻기','물으면 기록에서 센 답과 근거가 와요']];
 return <div className="four-steps"><div className="step-card on"><b>① 종이</b>{children}</div>
  {cards.map(([h,p])=><div className="step-card" key={h}><b>{h}</b>{bars('100%','70%','100%','55%')}<p className="muted">{p}</p></div>)}</div>;
}

// 처음 한 바퀴 띠: 이번 접속에서 빈 워크스페이스를 연 사람에게, 첫 답을 받을 때까지 보인다
export function FirstRunBand({tid,records,view,go}:{tid:number,records:number,view:string,go:(v:string)=>void}){
 const key=(k:string)=>`passo-first-${k}-${tid}`;
 const get=(k:string)=>{try{return sessionStorage.getItem(key(k));}catch{return null;}};
 const set=(k:string)=>{try{sessionStorage.setItem(key(k),'1');}catch{/* 저장하지 못해도 띠만 덜 보인다 */}};
 const [on,setOn]=useState(false),[home,setHome]=useState(false);
 useEffect(()=>{if(!records)set('run');setOn(!!get('run')&&!get('done'));setHome(!!get('home'));},[records]);  // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(()=>{if(records&&view==='home'&&get('run')){set('home');setHome(true);}if(view==='ask'&&records&&get('home')){/* 묻기에 들어오면 첫 답은 묻기 화면이 끝낸다 */}},[view,records]);  // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(()=>{const done=()=>{set('done');setOn(false);};window.addEventListener('passo-first-answer',done);return()=>window.removeEventListener('passo-first-answer',done);},[]);  // eslint-disable-line react-hooks/exhaustive-deps
 if(!on)return null;
 const done=1+(records>0?1:0)+(records>0&&home?1:0);
 return <nav className="first-band" aria-label="처음 한 바퀴">{STEPS.map(([s,v],i)=><button key={s} className={i<done?'done':i===done?'now':''} disabled={i>done} onClick={()=>go(v)}>{i<done?`${s} · 끝`:s}</button>)}<small className="muted">처음 한 바퀴</small></nav>;
}
