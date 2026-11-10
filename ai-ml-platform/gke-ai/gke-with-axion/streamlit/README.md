# GKE SRE & FinOps Agent (Google ADK + vLLM + Gemma 4 on GKE Axion)

Autonomous Kubernetes SRE & FinOps agent built with **Google ADK (Agent Development Kit)** (`google-adk`), **LiteLLM**, and **Streamlit**, powered by **Gemma 4 (`google/gemma-4-E4B-it`)** served on **vLLM Arm64 CPU** (`OMP_NUM_THREADS=14`, `VLLM_CPU_KVCACHE_SPACE=16`, `--dtype=bfloat16`) on **Google Cloud Axion (`c4a-standard-16`)** processors.

## Agent Package Structure (`axion_sre_agent/`)
- `axion_sre_agent/tools.py`: Defines 4 Google ADK tools:
  - `inspect_gke_axion_nodes()` — Live GKE node architecture (`arm64`), C4A machine shapes, and vCPU/DDR5 capacity via the Kubernetes Python client.
  - `inspect_namespace_workloads(namespace)` — Live pod health (`vllm-gemma4-0`, `streamlit-gemma4-ui`), vLLM CPU/memory limits, `OMP_NUM_THREADS=14` tuning, and `30Gi` `hyperdisk-balanced` PVC status.
  - `calculate_axion_vs_gpu_finops(model_size_billions, replicas, daily_agent_turns)` — Monthly TCO and per-1k-agent-turn cost comparison across Google Axion (`c4a-standard-16`), x86, and NVIDIA L4 GPU nodes.
  - `audit_and_generate_axion_manifest(workload_name, model_tag, vcpu_count, hyperdisk_size_gi)` — Generates tuned Arm64 GKE vLLM `StatefulSet` manifests and CPU thread/KV-cache settings (`OMP_NUM_THREADS=<vcpu - 2>`, `VLLM_CPU_KVCACHE_SPACE`).
- `axion_sre_agent/agent.py`: Exposes `root_agent` (`google.adk.agents.Agent` backed by `LiteLlm(model="openai/google/gemma-4-E4B-it", api_base="http://vllm-service:8000/v1")`) for both the Streamlit UI and `adk web` / `adk run axion_sre_agent`.
- `app.py`: Interactive Streamlit booth UI with 1-click KubeCon agent scenarios, expandable Google ADK tool traces, and side-by-side **Agent Mode** vs. **Raw vLLM Stream Mode**.

## Environment Variables
- `VLLM_BASE_URL`: Defaults to `http://vllm-service:8000/v1` (in-cluster GKE vLLM Service).
- `VLLM_MODEL`: Defaults to `google/gemma-4-E4B-it`.
- `AXION_MACHINE_TYPE`: Defaults to `c4a-standard-16`.
- `GKE_CLUSTER_NAME`: Defaults to `axion-cluster`.

## Running Locally with `uv` (Streamlit or Google ADK CLI)
```bash
uv sync

# Option A: Launch the KubeCon Booth Streamlit UI
uv run streamlit run app.py

# Option B: Launch the Google ADK Dev UI
uv run adk web
```
