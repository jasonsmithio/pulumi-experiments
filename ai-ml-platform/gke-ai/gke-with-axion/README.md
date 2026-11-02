# Inferencing with Gemma 4 on GKE using Google Axion (C4A) Processors & Pulumi

This repository demonstrates how to declaratively provision a **Google Kubernetes Engine (GKE)** cluster powered by **Google Axion** (`c4a-standard-16` Arm Neoverse V2) processors using **Pulumi (Python)**, attach persistent **Google Cloud Hyperdisk Balanced** storage (`30Gi`), automatically pull and tune **Gemma 4 4B** (`gemma4:4b-highthread` with `PARAMETER num_thread 14`) on **Ollama**, and serve a live **Streamlit** chat interface in-cluster.

---

## Architecture Overview

1. **Pulumi IaC (`__main__.py`)**:
   - Provisions a VPC-native GKE cluster (`axion-cluster`) with the Compute Engine Persistent Disk CSI driver (`hyperdisk-balanced`), GCS Fuse CSI driver, HTTP Load Balancing, and Gateway API enabled.
   - Creates an autoscaling Arm64 GKE Node Pool (`axion-nodepool`, `1–8` nodes) running `c4a-standard-16` VMs (`16` Arm Neoverse V2 vCPUs, `64 GB` DDR5 memory).
2. **Hyperdisk Balanced Storage (`k8s/hyperdisk-arm-sc.yaml`)**:
   - Defines the `hyperdisk-arm` `StorageClass` (`pd.csi.storage.gke.io`, `type: hyperdisk-balanced`, `WaitForFirstConsumer`) so `30Gi` model weights persist across pod restarts.
3. **Arm64 Ollama StatefulSet & Automated Gemma 4 Thread Tuning (`k8s/ollama-gemma4.yaml`)**:
   - Schedules the `ollama` `StatefulSet` strictly onto `kubernetes.io/arch: arm64` Axion nodes.
   - Mounts a `ConfigMap` (`gemma4-modelfile-config`) containing `modelfile.txt` (`FROM gemma4:4b`, `PARAMETER num_thread 14`) and runs an automatic `postStart` bootstrap script that pulls `gemma4:4b` and builds `gemma4:4b-highthread` on the `30Gi` Hyperdisk PVC.
   - Reserves `15` vCPUs (`limits.cpu: "15"`) for the Ollama container so `num_thread 14` saturates 14 Arm Neoverse V2 cores while leaving 2 vCPUs on the `c4a-standard-16` node for the GKE `kubelet` and network I/O.
4. **Multi-Arch Streamlit Frontend (`streamlit/`)**:
   - Uses `pulumi_docker_build` (`docker buildx`) to build and push a multi-arch (`linux/amd64`, `linux/arm64`) container image to Artifact Registry.
   - Deploys `streamlit-gemma4-ui` onto the GKE Axion node pool (`kubernetes.io/arch: arm64`), connected in-cluster to `http://ollama-service:11434/v1` via the OpenAI Python SDK, and exposes it through a Kubernetes `LoadBalancer` Service (`streamlit-gemma4-service`).

---

## Why Google Axion (C4A) for Gemma 4 Inferencing?

- **Up to 65% Better Price-Performance** and **60% Better Energy Efficiency** than comparable current-generation x86 VMs on Google Cloud.
- **Arm Neoverse V2 + CMN-700 Mesh + DDR5 Memory**: High memory bandwidth and low-latency core-to-core communication feed Gemma 4 weights to the CPU without bottlenecking token generation.
- **Titanium Offloads & Arm Kleidi AI Libraries**: Google's custom Titanium microcontrollers offload VPC networking and Hyperdisk storage I/O from the CPU, while Arm Kleidi SVE2/NEON kernels accelerate matrix multiplication in Ollama, `llama.cpp`, vLLM, and PyTorch.

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

3. Provision the GKE Axion cluster, Hyperdisk storage, Ollama `StatefulSet`, multi-arch Streamlit container, and LoadBalancer Service in a single step:

```bash
pulumi up
```

---

## Verifying & Benchmarking Gemma 4 on GKE Axion

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

> **Note:** If you want to manually inspect or customize the Modelfile inside the pod:
> ```bash
> kubectl exec -it ollama-0 -- bash
> ollama pull gemma4:4b
> ollama show --modelfile gemma4:4b > modelfile.txt
> # Ensure 'PARAMETER num_thread 14' is set in modelfile.txt
> ollama create -f ./modelfile.txt gemma4:4b-highthread
> ```

3. Open the live Streamlit Chat UI using the Pulumi output URL:

```bash
pulumi stack output streamlitUrl
```

In the Streamlit sidebar, you can toggle between **`gemma4:4b-highthread`** (14 Arm Neoverse V2 threads) and **`gemma4:4b`** (default threads) to compare live `tokens/second` throughput on your `c4a-standard-16` GKE node!

---

## Clean Up

To tear down the GKE cluster, Axion node pool, Hyperdisk storage, and Artifact Registry resources when finished:

```bash
pulumi destroy
```
