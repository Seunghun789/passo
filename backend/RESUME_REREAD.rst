마지막 워크스페이스 복원과 원본 다시 읽기
=========================================

구현 범위
---------
웹 apps/web, API·워커 backend, DB db/migrations/010_resume_and_reread.sql.
기존 Streamlit app.py·core/engine.py의 흐름을 참고했다. 기존 앱은 변경하지 않았다.

워크스페이스를 실제로 연 브라우저가 POST opened를 호출한다. 계정별 방문 기록은
비공개 DB 표에 저장한다. 번호 없는 주소는 접근 가능한 마지막 워크스페이스의
홈으로 연결된다. 권한이 사라진 공간은 제외하고, 방문 기록이 없으면 기존 순서를
사용한다. 조직 주인의 암묵적 접근도 지원하며 GET·링크 미리읽기는 방문을 기록하지 않는다.

올리기 → 올린 종이 → 보기 → 다시 읽기 → 모델 선택 → 읽기 시작으로 진행한다.
확정 기록이 있으면 먼저 확인 화면의 다시 확인으로 돌리기를 사용한다.
주인·확인하는 사람만 재읽기를 시작할 수 있다. PNG·JPEG·PDF, 4 MiB/30쪽 제한을
유지하며 기존 uploads/{tenant}-{source} 원본과 passo-originals 원본을 모두 지원한다.
CSV·Excel·WebP 재읽기는 이번 범위에 포함하지 않는다.

원본 해시·크기·선택 모델·원본 상태 revision을 새 작업에 고정한다. 같은 요청 키는
같은 작업을 반환하고 동일 원본의 동시 재읽기는 거절한다. 새 작업은 이전 작업의
모델 checkpoint를 재사용하지 않는다. 성공 시 같은 트랜잭션에서 기존 대기 카드와
기록을 새 결과로 교체하며 원본 파일은 유지한다. 교체 전 내용은 감사 이력에 남는다.
새 기록은 대기로 저장하고 새 읽은 값 카드를 만들며 자동 승인하지 않는다.
실패하면 기존 내용을 유지한다. 읽는 동안 사람이 수정·확정하면 source_changed로
종료하며 새 모델 결과를 덮어쓰지 않는다. 이전 confirm API로 확인 카드를 우회할 수 없다.

실서비스 적용
-------------
2026-11-16 실제 Supabase에 선행 009와 010을 한 트랜잭션으로 적용했다.
원래 저장소의 passo-worker-1로 로컬 워커를 교체했으며 이전 워커는 중지하고
자동 재시작을 해제했다. 로컬 웹·API는 3001/8003에서 검증했다.
실제 Auth·Supabase HTTP·Storage·새 워커·브라우저 검증 20개가 통과했다.
임시 로그인으로 마지막 워크스페이스 복원과 새 확인 카드 표시를 확인했다.
추출 결과는 임시 작업에 넣은 합성 checkpoint를 사용했으므로 실제 OCR·Anthropic
재추출 검증은 아니다. Vercel·Render 배포와 실제 모델 호출 확인은 남아 있다.
기존 10개 업무 표의 전후 행 수·해시가 같고 임시 계정·문서를 정리했다.
상세 증거는 artifacts/db-worker-20261116/review.html에 있다.
모델 목록은 기존 core/llm.py의 허용 목록을 따른다.

적용 순서: 기존 워커를 멈추고 001~009 적용 여부 확인 → 010 적용 → 새 API·워커
배포 → 새 웹 배포 → 임시 계정·문서로 실제 로그인 복원과 모델 재읽기를 확인한다.
이전 워커가 새 재읽기 작업을 처리하면 선택 모델을 무시하므로 웹보다 먼저 교체한다.
마이그레이션은 신규 테이블·컬럼과 함수 교체를 포함하며 재실행용이 아니다.

로컬 검증
---------
검증 명령은 저장소 루트에서 실행한다. Python 실행기는 테스트 의존성이 설치된
가상환경을 사용한다. 브라우저 검증은 localhost 18765/18766에 임시 서버를 시작하고
종료한다. 실제 Next.js와 가짜 Auth/API만 사용하며 외부 계정·업무 데이터·모델을 건드리지 않는다.

::

  npm ci --prefix apps/web
  PASSO_RLS_REPORT=artifacts/resume-reread/rls.json node tests/auth/rls.mjs
  python -m pytest tests/auth tests/documents -q
  python eval/verify_resume_reread_ui.py
  node tests/auth/origin.mjs
  npm run build --prefix apps/web

2026-11-16 결과: PGlite PostgreSQL 검증 225개, API·문서 Python 검증 59개,
Next.js 브라우저 검증 12개, Origin 검증 7개 통과. 확장 Python 평가를 포함하면
95개와 하위 사례 61개가 통과했다. 확장 평가 중 하나는 Git에서 제외된 기존
artifacts/stage1-live-20261113-r2/report.json을 필요로 한다. 이번 작업에서는
원래 저장소의 보존된 결과를 복사해 사용했으며 새 모델 평가 결과로 취급하지 않았다.

tasks.md의 Streamlit 체크 상태 144/146은 변경하지 않았다. 두 잔여 흐름의 새 웹
로컬 검증과 기존 Streamlit 수용 기준·실서비스 검증은 구분한다.
