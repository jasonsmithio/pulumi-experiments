#!/usr/bin/env bash
set -euo pipefail

AR_REPO="${AR_REPO:-streamlit}"
SERVICE_NAME="${SERVICE_NAME:-axion-gemma4-ui}"
GOOGLE_CLOUD_REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project)}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://vllm-service:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-google/gemma-4-4b-it}"

IMAGE_URI="${GOOGLE_CLOUD_REGION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/${AR_REPO}/${SERVICE_NAME}:latest"

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "${IMAGE_URI}" \
  --push .
