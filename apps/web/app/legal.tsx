// 개인정보처리방침 · 이용약관 페이지의 틀. 로그인 없이 누구나 본다
export const EFFECTIVE='2026년 11월 17일';
export const OPERATOR='준비 중';  // 운영 주체 · 개인정보 보호책임자 · 연락처. 실사용자를 받기 전에 채운다

export function Legal({title,children}:{title:string,children:React.ReactNode}){
 return <div className="legal-page"><header><a className="brand" href="/">passo</a><nav><a href="/terms">이용약관</a><a href="/privacy">개인정보처리방침</a></nav></header>
  <main className="legal"><h1>{title}</h1><p className="muted">시행일 {EFFECTIVE}</p>{children}</main></div>;
}

export function LegalLinks(){
 return <p className="legal-links"><a href="/terms">이용약관</a> · <a href="/privacy">개인정보처리방침</a></p>;
}
