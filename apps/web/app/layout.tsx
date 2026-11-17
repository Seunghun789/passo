// style.css가 층 순서를 맨 먼저 정한다: Astryx 테마(neutral) 값 위에 이 앱의 스타일(app)이 온다.
import './style.css';
import '@astryxdesign/theme-neutral/theme.css';
import type { Metadata } from 'next';
export const metadata: Metadata = {title:'passo',description:'종이는 그대로, 정리는 AI가 할게요.',robots:{index:false,follow:false}};
export default function Layout({children}:{children:React.ReactNode}) {
  return <html lang="ko"><body data-astryx-theme="neutral">{children}</body></html>;
}
