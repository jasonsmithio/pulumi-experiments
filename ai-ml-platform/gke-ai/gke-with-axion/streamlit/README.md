# GKE SRE & FinOps Agent (Google ADK + Gemma 4 on GKE Axion)

Autonomous Kubernetes SRE & FinOps agent built with **Google ADK (Agent Development Kit)** (`google-adk`), **LiteLLM**, and **Streamlit**, powered by **Gemma 4** (`gemma4:4b-highthread` vs. `gemma4:4b`) running on **Google Cloud Axion (`c4a-standard-16`)** Arm64 processors.

## Agent Package Structure (`axion_sre_agent/`)
- `axion_sre_agent/tools.py`: Defines 4 Google ADK tools:
  - `inspect_gke_axion_nodes()` — Live GKE node architecture (`arm64`), C4A machine shapes, and vCPU/DDR5 capacity via the Kubernetes Python client.
  - `inspect_namespace_workloads(namespace)` — Live pod health (`ollama-0`, `streamlit-gemma4-ui`), CPU/memory limits, and `30Gi` `hyperdisk-balanced` PVC status.
  - `calculate_axion_vs_gpu_finops(model_size_billions, replicas, daily_agent_turns)` — Monthly TCO and per-1k-agent-turn cost comparison across Google Axion (`c4a-standard-16`), x86, and NVIDIA L4 GPU nodes.
  - `audit_and_generate_axion_manifest(workload_name, model_tag, vcpu_count, hyperdisk_size_gi)` — Generates tuned Arm64 GKE `StatefulSet` manifests and `Modelfile` configs (`PARAMETER num_thread <vcpu - 2>`).
- `axion_sre_agent/agent.py`: Exposes `root_agent` (`google.adk.agents.Agent` backed by `LiteLlm(model="ollama_chat/gemma4:4b-highthread")`) for both the Streamlit UI and `adk web` / `adk run axion_sre_agent`.
- `app.py`: Interactive Streamlit booth UI with 1-click KubeCon agent scenarios, expandable Google ADK tool traces, and side-by-side **Agent Mode** vs. **Raw LLM Stream Mode**.

## Environment Variables
- `OLLAMA_BASE_URL`: Defaults to `http://ollama-service:11434/v1` (in-cluster GKE Service).
- `OLLAMA_MODEL`: Defaults to `gemma4:4b-highthread` (`PARAMETER num_thread 14`).
- `AXION_MACHINE_TYPE`: Defaults to `c4a-standard-16`.
- `GKE_CLUSTER_NAME`: Defaults to `axion-cluster`.

## Running Locally with Streamlit or Google ADK CLI
```bash
pip install -r requirements.txt

# Option A: Launch the KubeCon Booth Streamlit UI
streamlit run app.py

# Option B: Launch the Google ADK Dev UI
adk web
```
