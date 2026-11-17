'use client';
import {useEffect,useRef,useState} from 'react';
import {STEPS} from './steps';

const CASES:[string,string][]=[['제조 설비 점검','점검표 사진 · 이상 설비 챙기기'],['생산 검사','불량 기록 · 판정 기준'],
 ['유통 재고','재고 장부 · 부족 품목'],['공인중개사 메모','매물 메모 · 고객 연결']];
const SKEL=['100%','70%','100%','55%','100%'];

// 로그인하지 않은 첫 방문: 무슨 서비스인지 보여 주고 [바로 써 보기] · [로그인]으로 로그인 화면을 연다
export default function Landing(){
 const [note,setNote]=useState(''),[cases,setCases]=useState(false),[step,setStep]=useState(0),menu=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(!note)return;const t=setTimeout(()=>setNote(''),3200);return()=>clearTimeout(t);},[note]);
 useEffect(()=>{  // 네 칸에 차례로 불이 들어온다. ④ 다음에는 다시 ①
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const t=setInterval(()=>setStep(s=>(s+1)%4),2600);return()=>clearInterval(t);},[]);
 useEffect(()=>{if(!cases)return;
  const close=(e:MouseEvent|KeyboardEvent)=>{if(e instanceof KeyboardEvent?e.key==='Escape':!menu.current?.contains(e.target as Node))setCases(false);};
  document.addEventListener('mousedown',close);document.addEventListener('keydown',close);
  return()=>{document.removeEventListener('mousedown',close);document.removeEventListener('keydown',close);};},[cases]);
 return <div className="landing">
  <div className="glows" aria-hidden><i className="glow g1"/><i className="glow g2"/></div>
  <header className="landing-top"><div className="landing-inner">
   <a className="brand" href="/">passo</a>
   <nav>
    <div className="cases" ref={menu}><button className="text-button" aria-expanded={cases} onClick={()=>setCases(!cases)}>활용 사례</button>
     {cases&&<div className="cases-menu" role="menu">{CASES.map(([n,d])=><button role="menuitem" key={n} onClick={()=>{setCases(false);setNote(`${n} 활용 사례는 준비 중이에요. [바로 써 보기]로 내 종이를 올려 보세요.`);}}><b>{n}</b><small>{d}</small></button>)}</div>}</div>
    {['도큐먼트','회사소개'].map(n=><button key={n} className="text-button" onClick={()=>setNote(`${n}는 준비 중이에요.`)}>{n}</button>)}
   </nav>
   <a className="button login-button" href="/login">로그인</a>
  </div></header>
  <main className="landing-inner">
   <section className="hero"><h1>종이는 그대로,<br/>정리는 AI가 할게요</h1>
    <p>점검표 · 재고 장부 · 메모를 찍어 올리면<br/>AI가 칸을 찾아 표로 정리해요.<br/>애매한 값만 답하면 챙길 일과 답이 따라와요.</p>
    <a className="button primary go" href="/login">바로 써 보기</a><small className="note">이메일로 1분이면 시작해요</small></section>
   <ol className="steps">{STEPS.map(([h,p],i)=><li key={h} className={i===step?'on':''} onMouseEnter={()=>setStep(i)}><b>{h}</b>
    {i===0?<><div className="drop"><span>파일 고르기</span><small>사진이나 파일을 여기로 끌어 놓으세요</small></div><div className="fake">읽기 시작</div></>
     :<>{SKEL.map((w,j)=><i key={j} className="skel" style={{width:w}}/>)}<p>{p}</p></>}</li>)}</ol>
   <div className="loop"><span>④에서 다시 ① 종이로 · 올릴수록 묻는 건 줄고, 답은 정확해져요</span></div>
  </main>
  {note&&<p className="toast" role="status">{note}</p>}
 </div>;
}
