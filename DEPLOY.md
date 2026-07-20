# 배포 가이드 (GitHub Actions → Firebase Hosting)

`main` 브랜치에 push 하면 `.github/workflows/deploy.yml` 이 프론트엔드를 빌드해
Firebase Hosting 으로 **자동 배포**한다. 아래 1회 설정이 끝나면 이후엔 push 만으로 배포된다.

## 1. Firebase 프로젝트 준비
1. https://console.firebase.google.com 에서 프로젝트 생성.
2. **Hosting** 활성화.
3. 프로젝트 ID 확인 (예: `fashion-cardnews-1234`).
4. 로컬 `.firebaserc` 의 `your-project-id` 를 실제 프로젝트 ID 로 교체.

## 2. 서비스 계정 키 발급
Firebase 콘솔 → **프로젝트 설정 → 서비스 계정 → 새 비공개 키 생성** → JSON 다운로드.

> 팁: `firebase init hosting:github` 명령을 쓰면 서비스 계정 생성과 GitHub 시크릿 등록을
> 자동으로 처리해준다. (이미 워크플로우 파일이 있으므로, 물어보면 기존 파일 유지 선택)

## 3. GitHub Secrets 등록
저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에 아래 2개 추가:

| 시크릿 이름 | 값 |
|---|---|
| `FIREBASE_SERVICE_ACCOUNT` | 2단계에서 받은 **서비스 계정 JSON 전체** 붙여넣기 |
| `FIREBASE_PROJECT_ID` | Firebase 프로젝트 ID |

> 이 시크릿은 `.github/workflows/crawl.yml`(랭킹 크롤러)의 Firestore 적재에도 그대로 사용된다.

> 두 시크릿이 없으면 배포 워크플로우는 **자동으로 건너뛰며**(실패 아님), CI(빌드/테스트)만 동작한다.

## 4. 배포 확인
- `main` 에 push → 저장소 **Actions 탭**에서 `Deploy to Firebase Hosting` 실행 확인.
- 완료 후 `https://<project-id>.web.app` 에서 결과 확인.

## 워크플로우 요약
- `.github/workflows/ci.yml` — 빌드/테스트 (모든 push·PR)
- `.github/workflows/deploy.yml` — main push 시 Firebase Hosting 배포 (시크릿 있을 때만)
- Hosting 은 `frontend/dist` 를 서빙 (`firebase.json` 참고)
