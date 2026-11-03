# Agentic Inferencing with Gemma 4 & Google ADK on GKE Axion (C4A) Processors

This repository demonstrates how to declaratively provision a **Google Kubernetes Engine (GKE)** cluster powered by **Google Axion** (`c4a-standard-16` Arm Neoverse V2) processors using **Pulumi (Python)**, attach persistent **Google Cloud Hyperdisk Balanced** storage (`30Gi`), automatically pull and tune **Gemma 4 4B** (`gemma4:4b-highthread` with `PARAMETER num_thread 14`) on **Ollama**, and run an in-cluster **GKE SRE & FinOps Agent** built with **Google ADK (Agent Development Kit)** and **Streamlit**.

---

## Why Run Agents on Google Axion (C4A) with Gemma 4?

Autonomous agents execute frequent, bursty, multi-step **tool-calling loops** (inspecting Kubernetes nodes/pods, calculating FinOps TCO, auditing YAML manifests, and diagnosing cluster state). Running always-on 4B–9B parameter SLM agents on dedicated GPUs wastes scarce accelerator quota and budget during idle intervals between tool calls.

- **Up to 65% Better Price-Performance** and **60% Better Energy Efficiency** than comparable current-generation x86 VMs on Google Cloud.
- **Native Gemma 4 Function Calling on Arm64**: **Gemma 4** (`gemma4:4b-highthread`) pairs with **Google ADK (`google-adk`)** and **LiteLLM (`ollama_chat/gemma4:4b-highthread`)** to orchestrate multi-step tool calls entirely inside your GKE cluster—with zero external API token fees or GPU reservation bottlenecks.
- **Arm Neoverse V2 + Titanium Offloads + Arm Kleidi AI**: Google's custom Titanium microcontrollers offload VPC networking and Hyperdisk storage I/O from the CPU, while Arm Kleidi SVE2/NEON kernels accelerate matrix multiplication in Ollama, `llama.cpp`, vLLM, and PyTorch.

---

## Architecture Overview

1. **Pulumi IaC (`__main__.py`)**:
   - Provisions a VPC-native GKE cluster (`axion-cluster`) with the Compute Engine Persistent Disk CSI driver (`hyperdisk-balanced`), GCS Fuse CSI driver, HTTP Load Balancing, and Gateway API enabled.
   - Creates an autoscaling Arm64 GKE Node Pool (`axion-nodepool`, `1–8` nodes) running `c4a-standard-16` VMs (`16` Arm Neoverse V2 vCPUs, `64 GB` DDR5 memory).
   - Configures least-privilege, read-only Kubernetes RBAC (`ServiceAccount/axion-sre-agent-sa`, `ClusterRole/axion-sre-agent-reader`) so the in-cluster Google ADK agent can inspect live GKE nodes, pods, and PVCs.
2. **Hyperdisk Balanced Storage (`k8s/hyperdisk-arm-sc.yaml`)**:
   - Defines the `hyperdisk-arm` `StorageClass` (`pd.csi.storage.gke.io`, `type: hyperdisk-balanced`, `WaitForFirstConsumer`) so `30Gi` model weights persist across pod restarts.
3. **Arm64 Ollama StatefulSet & Automated Gemma 4 Thread Tuning (`k8s/ollama-gemma4.yaml`)**:
   - Schedules the `ollama` `StatefulSet` strictly onto `kubernetes.io/arch: arm64` Axion nodes.
   - Mounts a `ConfigMap` (`gemma4-modelfile-config`) containing `modelfile.txt` (`FROM gemma4:4b`, `PARAMETER num_thread 14`) and runs an automatic `postStart` bootstrap script that pulls `gemma4:4b` and builds `gemma4:4b-highthread` on the `30Gi` Hyperdisk PVC.
   - Reserves `15` vCPUs (`limits.cpu: "15"`) for the Ollama container so `num_thread 14` saturates 14 Arm Neoverse V2 cores while leaving 2 vCPUs on the `c4a-standard-16` node for the GKE `kubelet` and network I/O.
4. **Google ADK GKE SRE & FinOps Agent (`streamlit/axion_sre_agent/` & `streamlit/app.py`)**:
   - Defines `root_agent` (`gke_axion_sre_finops_agent`) using `google.adk.agents.Agent` and `LiteLlm(model="ollama_chat/gemma4:4b-highthread")` with 4 specialized tools:
     - `inspect_gke_axion_nodes()`: Queries live GKE node architecture (`arm64`), machine types (`c4a-standard-16`), and vCPU/DDR5 capacity.
     - `inspect_namespace_workloads(namespace)`: Inspects running pods (`ollama-0`, `streamlit-gemma4-ui`), CPU/memory limits, and `30Gi` `hyperdisk-arm` PVCs.
     - `calculate_axion_vs_gpu_finops(model_size_billions, replicas, daily_agent_turns)`: Computes monthly FinOps TCO and cost per 1,000 agent turns across Google Axion (`c4a-standard-16`), x86, and NVIDIA L4 GPU nodes.
     - `audit_and_generate_axion_manifest(workload_name, model_tag, vcpu_count, hyperdisk_size_gi)`: Generates tuned Arm64 GKE `StatefulSet` manifests and `Modelfile` thread allocations (`vcpu_count - 2`) for any C4A machine shape.
   - Exposes a Streamlit UI (`streamlit/app.py`) with 1-click KubeCon booth agent scenarios, expandable Google ADK tool execution traces, and live `tokens/sec` telemetry. Also compatible with `adk web` and `adk run axion_sre_agent`.

---

## Prerequisites

1. **Google Cloud SDK (`gcloud`)**, **`kubectl`**, **`gke-gcloud-auth-plugin`**, **Docker** (with `buildx`), and **Pulumi CLI** (`>= 3.0`) installed.
2. Export your environment variables:

```bash
export PROJECT_ID=<your-project-id>
export REGION=us-central1
export ZONE=${REGION}-a
export CLUSTER_NAME=axion-cluster
export NETWORK=default
```

3. Authenticate with Google Cloud and enable required APIs:

```bash
gcloud auth login
gcloud config set project $PROJECT_ID
gcloud config set compute/region $REGION
gcloud config set compute/zone $ZONE
gcloud auth application-default login
gcloud auth configure-docker ${REGION}-docker.pkg.dev

gcloud services enable \
  cloudresourcemanager.googleapis.com \
  compute.googleapis.com \
  container.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com
```

4. Grant standard logging, monitoring, and storage roles to the Compute Engine default service account:

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
GCE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:${GCE_SA} --role=roles/monitoring.metricWriter
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:${GCE_SA} --role=roles/stackdriver.resourceMetadata.writer
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:${GCE_SA} --role=roles/compute.storageAdmin
```

---

## Configure & Deploy with Pulumi

1. Create and activate a Python virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
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
pulumi config set ollamaModel gemma4:4b-highthread
```

3. Provision the GKE Axion cluster, Hyperdisk storage, Ollama `StatefulSet`, RBAC, and multi-arch Google ADK + Streamlit Agent UI in a single step:

```bash
pulumi up
```

---

## Running & Benchmarking the GKE SRE & FinOps Agent

1. Fetch cluster credentials and verify your `arm64` Axion nodes:

```bash
gcloud container clusters get-credentials $CLUSTER_NAME --region $REGION --project $PROJECT_ID
kubectl get nodes -o wide
```

2. Watch the automatic `gemma4:4b` and `gemma4:4b-highthread` bootstrap inside `ollama-0`:

```bash
kubectl exec -it ollama-0 -- cat /tmp/bootstrap-gemma4.log
kubectl exec -it ollama-0 -- ollama list
```

3. Open the live **GKE SRE & FinOps Agent UI** using the Pulumi output URL:

```bash
pulumi stack output streamlitUrl
```

In the UI, click any of the **4 KubeCon Booth Quick-Launch Scenarios** (or type your own question) and expand the **🔧 Google ADK Tool Execution Trace** to inspect the exact tool calls, JSON cluster telemetry, FinOps TCO calculations, and `tokens/sec` throughput on `gemma4:4b-highthread` vs. `gemma4:4b`!

---

## Clean Up

To tear down the GKE cluster, Axion node pool, Hyperdisk storage, and Artifact Registry resources when finished:

```bash
pulumi destroy
```
