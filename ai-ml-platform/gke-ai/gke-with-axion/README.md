# Agentic Inferencing with vLLM, Gemma 4 & Google ADK on GKE Axion (C4A) Processors

This repository demonstrates how to declaratively provision a **Google Kubernetes Engine (GKE)** cluster powered by **Google Axion** (`c4a-standard-16` Arm Neoverse V2) processors using **Pulumi (Python)**, attach persistent **Google Cloud Hyperdisk Balanced** storage (`30Gi`), serve **Gemma 4 4B (`google/gemma-4-4b-it`)** on **vLLM's Arm64 CPU backend** (`OMP_NUM_THREADS=14`, `VLLM_CPU_KVCACHE_SPACE=16`, `--dtype=bfloat16`), and run an in-cluster **GKE SRE & FinOps Agent** built with **Google ADK (Agent Development Kit)** and **Streamlit**.

---

## Why Run vLLM & Google ADK Agents on Google Axion (C4A) with Gemma 4?

Autonomous agents execute frequent, bursty, multi-step **tool-calling loops** (inspecting Kubernetes nodes/pods, calculating FinOps TCO, auditing YAML manifests, and diagnosing cluster state). Running always-on 4B–9B parameter SLM agents on dedicated GPUs wastes scarce accelerator quota and budget during idle intervals between tool calls.

- **Up to 65% Better Price-Performance** and **60% Better Energy Efficiency** than comparable current-generation x86 VMs on Google Cloud.
- **Cloud-Native vLLM on Arm64 CPU (`VLLM_TARGET_DEVICE=cpu`)**: **vLLM** leverages **Arm KleidiAI BF16/SVE2 kernels**, **PagedAttention** (`VLLM_CPU_KVCACHE_SPACE=16` in DDR5 memory), and OpenMP core binding (`OMP_NUM_THREADS=14`, `VLLM_CPU_OMP_THREADS_BIND="0-13"`) on `c4a-standard-16`—exposing a standard OpenAI-compatible `/v1/chat/completions` API with `--enable-auto-tool-choice`.
- **Google ADK (`google-adk`) + Gemma 4**: Connects directly to `http://vllm-service:8000/v1` via LiteLLM (`openai/google/gemma-4-4b-it`) to orchestrate multi-step Kubernetes SRE and FinOps tool calls entirely inside your GKE cluster.

---

## Architecture Overview

1. **Pulumi IaC (`__main__.py`)**:
   - Provisions a VPC-native GKE cluster (`axion-cluster`) with the Compute Engine Persistent Disk CSI driver (`hyperdisk-balanced`), GCS Fuse CSI driver, HTTP Load Balancing, and Gateway API enabled.
   - Creates an autoscaling Arm64 GKE Node Pool (`axion-nodepool`, `1–8` nodes) running `c4a-standard-16` VMs (`16` Arm Neoverse V2 vCPUs, `64 GB` DDR5 memory).
   - Configures least-privilege, read-only Kubernetes RBAC (`ServiceAccount/axion-sre-agent-sa`, `ClusterRole/axion-sre-agent-reader`) so the in-cluster Google ADK agent can inspect live GKE nodes, pods, and PVCs.
2. **Hyperdisk Balanced Storage (`k8s/hyperdisk-arm-sc.yaml`)**:
   - Defines the `hyperdisk-arm` `StorageClass` (`pd.csi.storage.gke.io`, `type: hyperdisk-balanced`, `WaitForFirstConsumer`) so `30Gi` HuggingFace model weights (`/root/.cache/huggingface`) persist across pod restarts.
3. **Arm64 vLLM StatefulSet & CPU Thread/KV-Cache Tuning (`k8s/vllm-axion-gemma4.yaml`)**:
   - Schedules the `vllm-gemma4` `StatefulSet` strictly onto `kubernetes.io/arch: arm64` Axion nodes.
   - Serves `google/gemma-4-4b-it` on port `8000` with `--dtype=bfloat16`, `--enable-auto-tool-choice`, and `--tool-call-parser=pythonic`.
   - Sets `OMP_NUM_THREADS=14` (`VLLM_CPU_OMP_THREADS_BIND="0-13"`) and `VLLM_CPU_KVCACHE_SPACE=16` to saturate 14 Arm Neoverse V2 cores while reserving 2 vCPUs on the `c4a-standard-16` node for the GKE `kubelet` and vLLM's async FastAPI HTTP loop.
4. **Google ADK GKE SRE & FinOps Agent (`streamlit/axion_sre_agent/` & `streamlit/app.py`)**:
   - Defines `root_agent` (`gke_axion_sre_finops_agent`) using `google.adk.agents.Agent` and `LiteLlm(model="openai/google/gemma-4-4b-it", api_base="http://vllm-service:8000/v1")` with 4 specialized tools:
     - `inspect_gke_axion_nodes()`: Queries live GKE node architecture (`arm64`), machine types (`c4a-standard-16`), and vCPU/DDR5 capacity.
     - `inspect_namespace_workloads(namespace)`: Inspects running pods (`vllm-gemma4-0`, `streamlit-gemma4-ui`), CPU/memory limits, and `30Gi` `hyperdisk-arm` PVCs.
     - `calculate_axion_vs_gpu_finops(model_size_billions, replicas, daily_agent_turns)`: Computes monthly FinOps TCO and cost per 1,000 agent turns across Google Axion (`c4a-standard-16`), x86, and NVIDIA L4 GPU nodes.
     - `audit_and_generate_axion_manifest(workload_name, model_tag, vcpu_count, hyperdisk_size_gi)`: Generates tuned Arm64 GKE vLLM `StatefulSet` manifests and `OMP_NUM_THREADS` / `VLLM_CPU_KVCACHE_SPACE` profiles for any C4A machine shape.
   - Exposes a Streamlit UI (`streamlit/app.py`) with 1-click KubeCon booth agent scenarios, expandable Google ADK tool execution traces, and live `tokens/sec` telemetry. Also compatible with `adk web` and `adk run axion_sre_agent`.

---

## Configure & Deploy with Pulumi

1. Sync the Python environment and dependencies using `uv`:

```bash
uv sync
```

2. Initialize (or select) your Pulumi stack and configure stack settings:

```bash
pulumi stack init dev
pulumi config set gcp:project $PROJECT_ID
pulumi config set gcp:region $REGION
pulumi config set gcp:zone $ZONE
pulumi config set gkeNetwork $NETWORK
pulumi config set clusterName $CLUSTER_NAME
pulumi config set nodepoolName axion-nodepool
pulumi config set nodesPerZone 2
pulumi config set mlMachines c4a-standard-16
pulumi config set vllmModel google/gemma-4-4b-it
```

3. (Optional) If pulling gated HuggingFace repositories, create `hf-secret` in the cluster (`optional: true` in the manifest):

```bash
kubectl create secret generic hf-secret --from-literal=hf_api_token=$HF_TOKEN
```

4. Provision the GKE Axion cluster, Hyperdisk storage, vLLM `StatefulSet`, RBAC, and multi-arch Google ADK + Streamlit Agent UI in a single step:

```bash
pulumi up
```

---

## Running & Benchmarking the GKE SRE & FinOps Agent

1. Fetch cluster credentials and verify your `arm64` Axion nodes and `vllm-gemma4-0` pod:

```bash
gcloud container clusters get-credentials $CLUSTER_NAME --region $REGION --project $PROJECT_ID
kubectl get nodes -o wide
kubectl get pods -o wide
```

2. Open the live **GKE SRE & FinOps Agent UI** using the Pulumi output URL:

```bash
pulumi stack output streamlitUrl
```

In the UI, click any of the **4 KubeCon Booth Quick-Launch Scenarios** (or type your own question) and expand the **🔧 Google ADK Tool Execution Trace** to inspect the exact tool calls, JSON cluster telemetry, FinOps TCO calculations, and `tokens/sec` throughput served by vLLM on `c4a-standard-16`!
