#!/usr/bin/env bash
# Google Cloud Shell 에서 한 번 실행한다. passo API 를 GitHub Actions 가 Cloud Run(도쿄)에 배포할 수 있게 준비한다.
# 키 파일 없이(Workload Identity Federation) 이 저장소 main 에서 돈 Actions 만 배포할 수 있다.
# 끝에 나오는 세 줄(GCP_PROJECT · GCP_SERVICE_ACCOUNT · GCP_WIF_PROVIDER)은 비밀값이 아니라 이름이다. GitHub 저장소 변수로 넣는다.
set -euo pipefail
PROJECT=${PROJECT:-$(gcloud config get-value project 2>/dev/null)}
[ -n "$PROJECT" ] || { echo "프로젝트를 먼저 고르세요: gcloud config set project <프로젝트 ID>"; exit 1; }
REPO=Seunghun789/passo
REGION=asia-northeast1
SA=passo-deployer
SAE=$SA@$PROJECT.iam.gserviceaccount.com
gcloud config set project "$PROJECT" >/dev/null
NUM=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
RUNTIME=$NUM-compute@developer.gserviceaccount.com  # API 가 돌 때 쓰는 기본 서비스 계정

echo "1/5 필요한 API 켜기"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com iamcredentials.googleapis.com sts.googleapis.com iam.googleapis.com

echo "2/5 컨테이너 저장소(도쿄)"
gcloud artifacts repositories describe passo --location=$REGION >/dev/null 2>&1 ||
  gcloud artifacts repositories create passo --repository-format=docker --location=$REGION --description="passo API"

echo "3/5 배포용 서비스 계정과 권한(Cloud Run 배포 · 컨테이너 올리기 · 런타임 계정으로 실행)"
gcloud iam service-accounts describe "$SAE" >/dev/null 2>&1 || gcloud iam service-accounts create $SA --display-name="passo GitHub deploy"
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SAE" --role=roles/run.admin --condition=None >/dev/null
gcloud artifacts repositories add-iam-policy-binding passo --location=$REGION --member="serviceAccount:$SAE" --role=roles/artifactregistry.writer >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME" --member="serviceAccount:$SAE" --role=roles/iam.serviceAccountUser >/dev/null

echo "4/5 GitHub Actions 연결(이 저장소 main 만)"
gcloud iam workload-identity-pools describe github --location=global >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools create github --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers describe passo --location=global --workload-identity-pool=github >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools providers create-oidc passo --location=global --workload-identity-pool=github \
    --issuer-uri=https://token.actions.githubusercontent.com \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository=='$REPO' && assertion.ref=='refs/heads/main'"
POOL=$(gcloud iam workload-identity-pools describe github --location=global --format='value(name)')
gcloud iam service-accounts add-iam-policy-binding "$SAE" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/$POOL/attribute.repository/$REPO" >/dev/null

echo "5/5 끝. 아래 세 줄을 GitHub 저장소 변수(Variables)로 넣으세요"
echo "GCP_PROJECT=$PROJECT"
echo "GCP_SERVICE_ACCOUNT=$SAE"
echo "GCP_WIF_PROVIDER=$(gcloud iam workload-identity-pools providers describe passo --location=global --workload-identity-pool=github --format='value(name)')"
