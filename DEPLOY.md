# 배포 체크리스트

passo는 세 부분으로 돈다. 로컬에서는 웹 3001, API 8003, 워커 Docker이고, 배포하면 아래 자리로 옮긴다.

| 부분 | 로컬 | 배포 | 하는 일 |
|---|---|---|---|
| 웹 | `apps/web` (3001) | Vercel | 화면, 로그인 |
| API 서버 | `backend/` (8003) | Render (`render.yaml`) | 기록 세기, 묻기·주간 요약 AI 호출, DB 함수 부르기 |
| 워커 | Docker `passo-worker-1` | Mac(지금) 또는 임대 서버 | 올린 종이 읽기(OCR·AI) |
| DB·파일 | Supabase | Supabase(그대로) | 기록, 원본 파일. 마이그레이션 001~021 적용됨 |

## 알아 둘 것 세 가지

### 1. 무료 서버의 메모리(512MB)

Render 무료 등급은 메모리가 512MB다. API 서버는 pandas와 anthropic을 함께 올리고, 기록이 많은 워크스페이스는 한 번에 읽어 센다. 모자라면 서버가 재시작되고, 그동안 화면에 "기록을 읽지 못했어요"가 보인다.

- 배포한 뒤 Render의 Metrics 화면에서 메모리를 본다.
- 400MB를 넘으면 메모리가 큰 유료 등급(Standard, 2GB)으로 올린다. Starter(월 $7)는 잠들지 않지만 메모리는 같은 512MB다.

### 2. 15분 뒤 잠들기

무료 등급은 15분 동안 요청이 없으면 잠든다. 잠든 뒤 첫 요청은 30초쯤 걸리고, 그동안 화면이 멈춘 것처럼 보인다.

- 혼자 확인할 때는 무료로 충분하다.
- 다른 사람이 쓰는 사용자 테스트 전에는 유료 등급으로 올린다.

### 3. 종이를 읽는 워커

Render에는 무료 백그라운드 워커가 없어서, 워커는 지금 Mac의 Docker에서 돈다. Mac을 끄거나 Docker를 멈추면 올린 종이가 "차례가 되면 자동으로 읽어요"에 머문다. 다시 켜면 이어서 읽는다.

- 혼자 확인할 때는 Mac에서 돌려도 된다.
- Mac을 꺼도 읽어야 하면 워커를 임대 서버로 옮긴다(Render 유료 Background Worker 또는 OCR을 돌릴 메모리 2GB 이상의 서버).

## 내가 할 일

키 값은 각 서비스 설정 화면에 직접 붙여 넣는다. 코드나 채팅에는 적지 않는다.

### Render (API 서버)

- [ ] Render에 로그인하고 GitHub 저장소를 연결한다.
- [ ] New → Blueprint로 `render.yaml`을 고른다. 서비스 이름은 `passo-dev-api`, 지역은 싱가포르로 만들어진다.
- [ ] Environment에 값을 넣는다.
  - `SUPABASE_URL`: Supabase 프로젝트 주소
  - `SUPABASE_PUBLISHABLE_KEY`: `sb_publishable_`로 시작하는 키
  - `SUPABASE_STORAGE_SECRET_KEY`: `sb_secret_`로 시작하는 키(원본 사진을 서버에서만 꺼낼 때 쓴다)
  - `RUNYOUR_API_KEY`: Runyour 키
  - `TZ`: `Asia/Seoul`(파일에 들어 있다. "오늘"을 한국 날짜로 센다)
  - `SUPABASE_SECRET_KEY`: `sb_secret_`로 시작하는 키(관리 화면이 모든 워크스페이스를 셀 때만 쓴다)
  - `ADMIN_EMAILS`: 관리 화면을 볼 사람의 로그인 메일(여럿이면 쉼표로)
- [ ] Settings → Build & Deploy에서 Branch는 `main`, Auto-Deploy는 After CI Checks Pass로 둔다. `main`에 푸시하면 GitHub Actions의 CI(API 테스트 · DB 권한 테스트 · 웹 빌드)가 돌고, 모두 통과한 커밋만 저절로 배포된다.
- [ ] 첫 배포가 끝나면 주소 뒤에 `/healthz`를 붙여 열었을 때 응답이 오는지 본다.
- [ ] 생긴 주소(예: `https://passo-dev-api.onrender.com`)를 적어 둔다.

### Vercel (웹)

- [ ] Vercel에서 저장소를 연결하고 Root Directory를 `apps/web`으로 정한다.
- [ ] Environment Variables에 값을 넣는다.
  - `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`: Render와 같은 값
  - `PASSO_API_URL`: 위에서 적어 둔 Render 주소
  - `PASSO_SITE_URL`: Vercel이 준 웹 주소(예: `https://passo.vercel.app`). 회원가입 · 비밀번호 찾기 · Google · 카카오 로그인이 이 주소로 돌아온다
  - `PASSO_KAKAO`: 카카오 로그인을 켤 때만 `on`
- [ ] 배포한다.

### Supabase (로그인 주소)

- [ ] Authentication → URL Configuration의 Site URL을 Vercel 웹 주소로 바꾼다.
- [ ] Redirect URLs에 `https://(웹 주소)/auth/callback`을 더한다. 빠지면 Google 로그인 · 가입 확인 메일 · 비밀번호 찾기 뒤 돌아오지 못한다.
- [ ] Authentication → Providers → Email에서 "Confirm email"을 켠 채로 둔다(메일 확인을 마친 사람만 기록에 잇는다).
- [ ] 무료 Supabase의 기본 메일은 한 시간에 몇 통만 보낸다. 사용자 테스트 전에 Authentication → SMTP에 메일 서비스를 연결한다.
- [ ] 카카오 로그인을 쓸 때: Kakao Developers에서 앱을 만들고, Supabase Authentication → Providers → Kakao에 REST API 키 · Client Secret을 넣는다.

### 워커

- [ ] Mac에서 계속 돌릴 때: Docker Desktop을 켜 두고 `docker compose -p passo up -d worker`가 떠 있는지 본다.
- [ ] 임대 서버로 옮길 때: 서버를 정한 뒤 옮긴다(`backend/worker.env.example`의 값을 그 서버에 넣는다).

### 배포 뒤 확인

- [ ] 웹 주소에서 [이메일로 로그인] → 홈이 열린다.
- [ ] [올리기]에서 사진 한 장 → [읽기 시작] → 몇 분 안에 "기록에 반영했어요"가 보인다(워커가 켜져 있을 때).
- [ ] [묻기]에서 예시 질문을 누르고 [묻기] → 답과 "근거 기록 N줄"이 보인다.
- [ ] 홈에서 [이번 주 요약 만들기] → 요약 문장이 보인다.
- [ ] Render Metrics에서 메모리가 400MB 아래인지 본다.
