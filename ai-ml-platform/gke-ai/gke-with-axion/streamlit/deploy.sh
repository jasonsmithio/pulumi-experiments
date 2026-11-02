#!/usr/bin/env bash
set -euo pipefail

AR_REPO="${AR_REPO:-streamlit}"
SERVICE_NAME="${SERVICE_NAME:-axion-inference-app}"
GOOGLE_CLOUD_REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project)}"
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://ollama-service:11434/v1}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:4b-highthread}"

IMAGE_URI="${GOOGLE_CLOUD_REGION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/${AR_REPO}/${SERVICE_NAME}:latest"

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "${IMAGE_URI}" \
  --push .
