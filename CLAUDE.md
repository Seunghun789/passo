# CLAUDE.md

## 내 프로젝트 규칙

1. 작업을 시작하기 전에 PRD.md 를 먼저 읽는다. tasks.md 가 있으면 함께 읽는다. 범위·비전이 걸린 판단은 메인 PRD(`~/Desktop/papertolveai/PRD_Tolve_v3.1_SaaS.md`)도 본다.
2. 어려운 말을 쓰면 바로 뒤에 뜻을 한 줄로 풀어 준다.
3. AI가 판단해 반영하고 근거를 남긴다. 하네스(판단을 검사하는 틀)가 의심되는 것만 사람에게 묻고, 반영한 것은 언제든 되돌릴 수 있다. 사람 개입을 최소로 줄이면서 빠른 응답과 안정성을 함께 지킨다. 이 원칙을 벗어나는 기능은 넣지 않는다.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 이 폴더

passo(손으로 적은 종이 → AI가 판단해 반영 → 위험한 값만 사람에게 확인 → 묻기·대시보드·자동화)의 기획 문서와 서비스 코드가 있다.

- 구성: 웹 `apps/web`(Next.js, Vercel), API `backend/`(FastAPI, Google Cloud Run 도쿄), 종이를 읽는 워커 `backend/worker.py`(Mac의 Docker `passo-worker-1`), DB·원본 파일 Supabase(도쿄). 배포 자리와 키 넣는 곳은 `DEPLOY.md`.
- 코드: `apps/web`(화면), `backend/`(API·워커), `core/llm.py`(모든 Claude 호출), `core/ocr.py`(사진 속 위치·읽지 않은 곳), `core/engine.py`(규칙·계산·제안), `app.py`(초기 Streamlit 프로토타입)
- 배포: `main`에 푸시하면 CI가 시험한 뒤 API를 Cloud Run에 배포하고, 웹은 Vercel이 배포한다. DB 마이그레이션(`db/migrations/`)은 따로 적용한다.
- 워커: `docker compose -p passo up -d worker`. `backend/`·`core/`를 바꾸면 `--build`를 붙여 다시 만든다. 워커가 꺼져 있으면 올린 종이가 "읽기 대기"에 머문다.
- DB 스키마: `db/schema.sql` 다음에 `db/migrations/`를 번호 순서로 적용한다.
- 사진 위치를 찾는 OCR 모델은 처음 사진을 읽을 때 `models/ocr/`(git 제외)에 받는다.
- 확인: `python -m pytest tests -q`(API·워커), `apps/web`에서 `npm run typecheck`. 읽기 품질은 `python -m eval.grade`(정답지 채점, Claude를 실제로 불러 비용이 든다), 위치는 `eval/place.py`로 잰다.
- 가설 검증용 더미 데이터: `dummy/`(제조 설비 점검 CSV·`photos/`, `samples/`의 생산 검사·유통 재고·공인중개사 메모, `db/`의 더미 계정 내보내기)
- 로그인은 Supabase Auth(Google, 이메일·비밀번호, 카카오)다. 관리자는 로그인 메일이 API의 `ADMIN_EMAILS`에 있는 사람이다.
- 기획 문서: `PRD.md`, `tasks.md`, `build-decisions.md`, `progress.md`, `backlog.md`(더할 새 기능 후보), `idea/`

## 문서 작성 규칙

- 수용 기준은 "무엇을 넣거나 누르면 → 화면에 무엇이 보인다" 모양이고, 사용자 흐름에 있는 버튼·칸 이름만 쓴다.
- 문서에는 현재 내용의 결론만 쓴다. 변경 이력, 상태, 이전 버전 비교, 점검·검증 메모는 파일에 넣지 않고 대화로만 한다.

## 상황별 규칙 (목차 — 규칙은 .claude/rules/ 에 있음)

- 화면을 만들 때 → .claude/rules/screen.md
- 기능이나 도구를 더할 때 → .claude/rules/scope.md
- 문서를 쓰거나 고칠 때 → .claude/rules/docs.md

CLAUDE.md 의 절대 규칙이 rules 파일보다 항상 우선한다.
