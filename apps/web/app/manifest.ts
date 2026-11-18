import type { MetadataRoute } from 'next';
// 폰 홈 화면에 설치하면 주소창 없이 열린다(PWA). 앱 화면은 PRD §4 사용자 흐름 (앱)
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'passo',
    short_name: 'passo',
    description: '종이는 그대로, 정리는 AI가 할게요.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    orientation: 'portrait',
    background_color: '#ffffff',
    theme_color: '#ffffff',
    lang: 'ko',
    icons: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
      { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  };
}
