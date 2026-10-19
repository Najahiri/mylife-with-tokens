#!/usr/bin/env bash
set -euo pipefail

# Run inside Swiss AI's Apertus 1.5 vLLM image; no decision adapter is loaded.
: "${CHAT_API_KEY:?Set CHAT_API_KEY}"
chat_model="${CHAT_MODEL_ID:-swiss-ai/Apertus-v1.5-8B}"
chat_source="${CHAT_MODEL_PATH:-$chat_model}"
if [[ "${CHAT_DISABLE_FUSED_ALLREDUCE_RMS:-false}" == "true" ]]; then
    set -- --compilation-config.pass_config.fuse_allreduce_rms false "$@"
fi
if [[ -n "${CHAT_REVISION:-}" && -z "${CHAT_MODEL_PATH:-}" ]]; then
    set -- --revision "$CHAT_REVISION" "$@"
fi
exec vllm serve "$chat_source" \
    --served-model-name "$chat_model" \
    --host 0.0.0.0 --port "${PORT:-8000}" \
    --api-key "$CHAT_API_KEY" \
    --chat-template-content-format string \
    --enable-auto-tool-choice --tool-call-parser apertus \
    --gpu-memory-utilization "${CHAT_GPU_MEMORY_UTILIZATION:-0.9}" \
    --max-model-len "${CHAT_MAX_MODEL_LEN:-8192}" \
    --tensor-parallel-size "${CHAT_TENSOR_PARALLEL_SIZE:-1}" \
    --max-num-seqs "${CHAT_MAX_NUM_SEQS:-1}" \
    --dtype "${CHAT_DTYPE:-bfloat16}" \
    "$@"
