# card-ilovefashion

패션 카드뉴스 프로젝트.

## 개발 환경 자동화

이 저장소는 Claude Code로 다음 자동화가 구성되어 있습니다.

### 자동 커밋 & 푸시
Claude Code 작업 중 코드 수정(Edit/Write)이 발생하면, 턴이 끝날 때 자동으로 커밋 후 `origin/main`에 푸시됩니다.

- 훅 스크립트: `.claude/hooks/auto-commit-push.sh`
- 훅 설정: `.claude/settings.local.json` (Stop 훅)
- 변경 사항이 없으면 아무 것도 하지 않습니다.

### CI (GitHub Actions)
`.github/workflows/ci.yml`

- `main` 브랜치 push 또는 PR 시 실행됩니다.
- `package.json`이 있으면 자동으로 `npm ci → lint → test → build`를 수행합니다 (정의된 스크립트만).
- 아직 `package.json`이 없으면 통과 처리하며, 코드가 추가되면 별도 설정 없이 검증이 시작됩니다.

## 시작하기

프로젝트 스택(예: React/Vite, Next.js, 정적 사이트)을 정한 뒤 코드를 추가하면 CI가 자동으로 동작합니다.
