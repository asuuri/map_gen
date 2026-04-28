#!/usr/bin/env bash
# Build dist/, package into a Docker image, push to local registry, and roll out.
set -euo pipefail

IMAGE="minka:32000/kartat:latest"

python generate_index.py --title "Kartat"
docker build -t "$IMAGE" .
docker push "$IMAGE"
kubectl rollout restart deployment/kartat -n kartat
kubectl rollout status deployment/kartat -n kartat
