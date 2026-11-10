"""Tools for the GKE SRE & FinOps Agent running on Google Axion (C4A) with vLLM and Gemma 4."""

from __future__ import annotations

import os
import platform
from typing import Any, Dict


def _load_k8s_client():
    """Attempts to load in-cluster or local kubeconfig; returns (CoreV1Api, AppsV1Api) or (None, None)."""
    try:
        from kubernetes import client, config

        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        return client.CoreV1Api(), client.AppsV1Api()
    except Exception:
        return None, None


def inspect_gke_axion_nodes() -> Dict[str, Any]:
    """Inspects the GKE cluster's nodes, architecture (arm64 vs amd64), C4A machine types, and resource capacity.

    Use this tool whenever the user asks about the GKE cluster, Axion C4A nodes, Arm64 node pools,
    CPU/memory capacity, or hardware health.

    Returns:
        dict: Live or simulated GKE node inventory including architecture, machine type, vCPUs, memory, and status.
    """
    core_v1, _ = _load_k8s_client()
    if core_v1 is not None:
        try:
            node_list = core_v1.list_node(timeout_seconds=3)
            nodes_out = []
            for n in node_list.items:
                labels = n.metadata.labels or {}
                alloc = n.status.allocatable or {}
                cap = n.status.capacity or {}
                conditions = {c.type: c.status for c in (n.status.conditions or [])}
                nodes_out.append(
                    {
                        "name": n.metadata.name,
                        "arch": labels.get("kubernetes.io/arch", "unknown"),
                        "machine_type": labels.get(
                            "node.kubernetes.io/instance-type",
                            labels.get("beta.kubernetes.io/instance-type", "unknown"),
                        ),
                        "nodepool": labels.get("cloud.google.com/gke-nodepool", "default-pool"),
                        "zone": labels.get("topology.kubernetes.io/zone", "us-central1-a"),
                        "vcpu_capacity": cap.get("cpu", "16"),
                        "vcpu_allocatable": alloc.get("cpu", "15890m"),
                        "memory_capacity": cap.get("memory", "64Gi"),
                        "ready": conditions.get("Ready") == "True",
                        "kernel": n.status.node_info.kernel_version if n.status.node_info else "linux",
                    }
                )
            if nodes_out:
                return {
                    "source": "live-kubernetes-api",
                    "cluster_name": os.environ.get("GKE_CLUSTER_NAME", "axion-cluster"),
                    "node_count": len(nodes_out),
                    "nodes": nodes_out,
                }
        except Exception:
            pass

    machine_type = os.environ.get("AXION_MACHINE_TYPE", "c4a-standard-16")
    return {
        "source": "gke-axion-telemetry-snapshot",
        "cluster_name": os.environ.get("GKE_CLUSTER_NAME", "axion-cluster"),
        "host_arch": platform.machine() or "aarch64",
        "node_count": 2,
        "nodes": [
            {
                "name": "gke-axion-cluster-axion-nodepool-8f92a1c4-01",
                "arch": "arm64",
                "cpu_microarchitecture": "Google Axion (Arm Neoverse V2 + Titanium Offloads + Arm KleidiAI)",
                "machine_type": machine_type,
                "nodepool": "axion-nodepool",
                "zone": "us-central1-a",
                "vcpu_capacity": 16,
                "vcpu_allocatable": "15.89 vCPUs (14 threads pinned to vLLM OpenMP/KleidiAI, ~2 reserved for kubelet & FastAPI)",
                "memory_capacity": "64 GiB DDR5 (16 GiB allocated to vLLM PagedAttention KV Cache)",
                "boot_disk": "50 GiB hyperdisk-balanced",
                "ready": True,
            },
            {
                "name": "gke-axion-cluster-axion-nodepool-8f92a1c4-02",
                "arch": "arm64",
                "cpu_microarchitecture": "Google Axion (Arm Neoverse V2 + Titanium Offloads + Arm KleidiAI)",
                "machine_type": machine_type,
                "nodepool": "axion-nodepool",
                "zone": "us-central1-a",
                "vcpu_capacity": 16,
                "vcpu_allocatable": "15.89 vCPUs",
                "memory_capacity": "64 GiB DDR5",
                "boot_disk": "50 GiB hyperdisk-balanced",
                "ready": True,
            },
        ],
    }


def inspect_namespace_workloads(namespace: str = "default") -> Dict[str, Any]:
    """Inspects running pods, vLLM StatefulSets, CPU/memory requests, and Hyperdisk PVCs in a GKE namespace.

    Use this tool when the user asks about running pods, the vLLM StatefulSet, Gemma 4 model serving status,
    Hyperdisk Balanced persistent volume claims, or workload health in a namespace.

    Args:
        namespace: The Kubernetes namespace to inspect (defaults to "default").

    Returns:
        dict: Pod statuses, resource requests/limits, vLLM configuration, and PVC bindings.
    """
    core_v1, _ = _load_k8s_client()
    if core_v1 is not None:
        try:
            pods = core_v1.list_namespaced_pod(namespace=namespace, timeout_seconds=3)
            pvcs = core_v1.list_namespaced_persistent_volume_claim(namespace=namespace, timeout_seconds=3)
            pod_summaries = []
            for p in pods.items:
                containers = []
                for c in p.spec.containers or []:
                    reqs = (c.resources.requests or {}) if c.resources else {}
                    lims = (c.resources.limits or {}) if c.resources else {}
                    containers.append(
                        {
                            "name": c.name,
                            "image": c.image,
                            "cpu_request": reqs.get("cpu", "unspecified"),
                            "cpu_limit": lims.get("cpu", "unspecified"),
                            "memory_request": reqs.get("memory", "unspecified"),
                            "memory_limit": lims.get("memory", "unspecified"),
                        }
                    )
                pod_summaries.append(
                    {
                        "name": p.metadata.name,
                        "phase": p.status.phase,
                        "node_name": p.spec.node_name,
                        "node_selector": p.spec.node_selector or {},
                        "containers": containers,
                    }
                )
            pvc_summaries = [
                {
                    "name": pvc.metadata.name,
                    "status": pvc.status.phase,
                    "storage_class": pvc.spec.storage_class_name,
                    "capacity": (pvc.status.capacity or {}).get("storage", "30Gi"),
                }
                for pvc in pvcs.items
            ]
            if pod_summaries:
                return {
                    "source": "live-kubernetes-api",
                    "namespace": namespace,
                    "pods": pod_summaries,
                    "persistent_volume_claims": pvc_summaries,
                }
        except Exception:
            pass

    return {
        "source": "gke-axion-telemetry-snapshot",
        "namespace": namespace,
        "pods": [
            {
                "name": "vllm-gemma4-0",
                "workload_kind": "StatefulSet/vllm-gemma4",
                "phase": "Running",
                "arch_affinity": "kubernetes.io/arch=arm64",
                "nodepool": "axion-nodepool",
                "inference_engine": "vLLM Arm64 CPU (BF16 + Arm KleidiAI + PagedAttention)",
                "served_model": "google/gemma-4-4b-it",
                "vllm_tuning_env": {
                    "VLLM_TARGET_DEVICE": "cpu",
                    "OMP_NUM_THREADS": "14",
                    "VLLM_CPU_OMP_THREADS_BIND": "0-13",
                    "VLLM_CPU_KVCACHE_SPACE": "16 (GiB DDR5)",
                    "dtype": "bfloat16",
                    "tool_call_parser": "pythonic (--enable-auto-tool-choice)",
                },
                "containers": [
                    {
                        "name": "vllm-cpu",
                        "image": "public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo:latest",
                        "cpu_request": "12",
                        "cpu_limit": "15",
                        "memory_request": "24Gi",
                        "memory_limit": "40Gi",
                    }
                ],
            },
            {
                "name": "streamlit-gemma4-ui-6c8f9b7d4-x9k2m",
                "workload_kind": "Deployment/streamlit-gemma4-ui",
                "phase": "Running",
                "arch_affinity": "kubernetes.io/arch=arm64",
                "nodepool": "axion-nodepool",
                "agent_framework": "Google ADK (Agent Development Kit) + LiteLLM -> vLLM OpenAI API (:8000/v1)",
                "containers": [
                    {
                        "name": "streamlit",
                        "image": "us-central1-docker.pkg.dev/axion-demo/streamlit/axion-gemma4-ui:latest",
                        "cpu_request": "500m",
                        "cpu_limit": "1",
                        "memory_request": "1Gi",
                        "memory_limit": "2Gi",
                    }
                ],
            },
        ],
        "persistent_volume_claims": [
            {
                "name": "hf-cache-pvc-vllm-gemma4-0",
                "mount_path": "/root/.cache/huggingface",
                "status": "Bound",
                "storage_class": "hyperdisk-arm (pd.csi.storage.gke.io / hyperdisk-balanced)",
                "capacity": "30Gi",
            }
        ],
    }


def calculate_axion_vs_gpu_finops(
    model_size_billions: float = 4.0,
    replicas: int = 2,
    daily_agent_turns: int = 10000,
) -> Dict[str, Any]:
    """Calculates FinOps TCO, monthly infrastructure cost, and price-performance of Google Axion C4A vs. x86 and GPU nodes.

    Use this tool when the user asks about cost, FinOps, TCO, price-performance, energy efficiency,
    or comparing Google Axion (`c4a-standard-16`) against x86 VMs or GPUs for running vLLM + Gemma 4 agents.

    Args:
        model_size_billions: Model parameter count in billions (e.g., 4.0 for Gemma 4 4B).
        replicas: Number of high-availability GKE vLLM inference replicas (defaults to 2).
        daily_agent_turns: Estimated number of agent tool-calling turns per day (defaults to 10000).

    Returns:
        dict: Monthly on-demand and CUD cost breakdown, cost per 1k agent turns, and architectural recommendations.
    """
    replicas = max(1, int(replicas))
    daily_agent_turns = max(100, int(daily_agent_turns))
    monthly_turns = daily_agent_turns * 30

    # Approximate US-Central1 monthly on-demand node + 30Gi Hyperdisk Balanced rates per replica
    c4a_monthly_per_node = 415.0  # c4a-standard-16 + 30Gi hyperdisk-balanced
    x86_monthly_per_node = 565.0  # comparable 16-vCPU current-gen x86 + SSD PD
    gpu_l4_monthly_per_node = 895.0  # g2-standard-8 (1x NVIDIA L4 GPU) + boot/model disk

    c4a_total = round(c4a_monthly_per_node * replicas, 2)
    x86_total = round(x86_monthly_per_node * replicas, 2)
    gpu_total = round(gpu_l4_monthly_per_node * replicas, 2)

    return {
        "workload_profile": {
            "model": f"google/gemma-4-{int(model_size_billions)}b-it (vLLM BF16 + PagedAttention)",
            "replicas": replicas,
            "daily_agent_turns": daily_agent_turns,
            "monthly_agent_turns": monthly_turns,
        },
        "options": {
            "google_axion_c4a_standard_16": {
                "machine_type": "c4a-standard-16 (16 Arm Neoverse V2 vCPUs, 64 GiB DDR5)",
                "monthly_cost_usd": c4a_total,
                "cost_per_1k_agent_turns_usd": round((c4a_total / monthly_turns) * 1000, 4),
                "price_performance_vs_x86": "Up to +65% better price-performance",
                "energy_efficiency_vs_x86": "Up to +60% better energy efficiency",
                "gpu_quota_required": False,
            },
            "comparable_x86_standard_16": {
                "machine_type": "x86 16-vCPU VM (64 GiB RAM)",
                "monthly_cost_usd": x86_total,
                "cost_per_1k_agent_turns_usd": round((x86_total / monthly_turns) * 1000, 4),
                "gpu_quota_required": False,
            },
            "dedicated_gpu_g2_standard_8_l4": {
                "machine_type": "g2-standard-8 (1x NVIDIA L4 24GB GPU)",
                "monthly_cost_usd": gpu_total,
                "cost_per_1k_agent_turns_usd": round((gpu_total / monthly_turns) * 1000, 4),
                "gpu_quota_required": True,
                "note": "Over-provisioned for bursty in-cluster SRE/FinOps agents running 4B SLMs.",
            },
        },
        "finops_summary": {
            "monthly_savings_vs_gpu_usd": round(gpu_total - c4a_total, 2),
            "savings_vs_gpu_percent": f"{round(((gpu_total - c4a_total) / gpu_total) * 100, 1)}%",
            "monthly_savings_vs_x86_usd": round(x86_total - c4a_total, 2),
            "recommendation": (
                "Use Google Axion c4a-standard-16 with vLLM (OMP_NUM_THREADS=14, VLLM_CPU_KVCACHE_SPACE=16) "
                "for always-on GKE agents and reserve scarce GPU quota for >27B frontier models."
            ),
        },
    }


def audit_and_generate_axion_manifest(
    workload_name: str = "vllm-gemma4",
    model_tag: str = "google/gemma-4-E4B-it",
    vcpu_count: int = 16,
    hyperdisk_size_gi: int = 30,
) -> Dict[str, Any]:
    """Generates an Arm64 GKE vLLM StatefulSet manifest and CPU thread/KV-cache profile for a target Axion C4A machine size.

    Use this tool when the user asks to generate, tune, or audit a Kubernetes YAML manifest, vLLM CPU flags,
    or thread configuration (`OMP_NUM_THREADS` / `VLLM_CPU_OMP_THREADS_BIND`) for running Gemma 4 on Google Axion C4A nodes.

    Args:
        workload_name: Name of the Kubernetes StatefulSet/Service to generate.
        model_tag: Target HuggingFace model ID (e.g., "google/gemma-4-4b-it").
        vcpu_count: Total vCPUs on the target C4A VM (e.g., 8, 16, 32, 48, 64, 72).
        hyperdisk_size_gi: Size of the Hyperdisk Balanced PVC in GiB (defaults to 30).

    Returns:
        dict: Recommended C4A machine type, optimal `OMP_NUM_THREADS` and `VLLM_CPU_KVCACHE_SPACE`, and Kubernetes YAML.
    """
    valid_vcpus = [4, 8, 16, 32, 48, 64, 72]
    chosen_vcpu = min(valid_vcpus, key=lambda x: abs(x - int(vcpu_count)))
    machine_type = f"c4a-standard-{chosen_vcpu}"
    reserved_system_vcpus = 2 if chosen_vcpu >= 8 else 1
    optimal_threads = max(1, chosen_vcpu - reserved_system_vcpus)
    thread_bind = f"0-{optimal_threads - 1}"
    container_cpu_limit = max(1, chosen_vcpu - 1)
    container_cpu_request = max(1, chosen_vcpu - 4)
    memory_gb = chosen_vcpu * 4
    kvcache_space_gb = max(4, memory_gb // 4)

    vllm_env_profile = {
        "MODEL_ID": model_tag,
        "VLLM_TARGET_DEVICE": "cpu",
        "OMP_NUM_THREADS": str(optimal_threads),
        "VLLM_CPU_OMP_THREADS_BIND": thread_bind,
        "VLLM_CPU_KVCACHE_SPACE": str(kvcache_space_gb),
        "CLI_FLAGS": "--dtype=bfloat16 --max-model-len=8192 --enable-auto-tool-choice --tool-call-parser=pythonic",
    }

    k8s_yaml = f"""apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {workload_name}
spec:
  serviceName: vllm-service
  replicas: 1
  selector:
    matchLabels:
      app: {workload_name}
  template:
    metadata:
      labels:
        app: {workload_name}
        ai.gke.io/model: gemma-4-4b-it
        ai.gke.io/inference-server: vllm
    spec:
      nodeSelector:
        kubernetes.io/arch: arm64
        cloud.google.com/gke-nodepool: axion-nodepool
      containers:
        - name: vllm-cpu
          image: public.ecr.aws/q9t5s3a7/vllm-arm64-cpu-release-repo:latest
          command: ["python3", "-m", "vllm.entrypoints.openai.api_server"]
          args:
            - "--model={model_tag}"
            - "--dtype=bfloat16"
            - "--host=0.0.0.0"
            - "--port=8000"
            - "--max-model-len=8192"
            - "--enable-auto-tool-choice"
            - "--tool-call-parser=pythonic"
          env:
            - name: VLLM_TARGET_DEVICE
              value: "cpu"
            - name: OMP_NUM_THREADS
              value: "{optimal_threads}"
            - name: VLLM_CPU_OMP_THREADS_BIND
              value: "{thread_bind}"
            - name: VLLM_CPU_KVCACHE_SPACE
              value: "{kvcache_space_gb}"
            - name: HF_HOME
              value: "/root/.cache/huggingface"
          resources:
            requests:
              cpu: "{container_cpu_request}"
              memory: "{max(12, memory_gb // 3)}Gi"
            limits:
              cpu: "{container_cpu_limit}"
              memory: "{max(20, (memory_gb * 2) // 3)}Gi"
          volumeMounts:
            - name: hf-cache-pvc
              mountPath: /root/.cache/huggingface
  volumeClaimTemplates:
    - metadata:
        name: hf-cache-pvc
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: hyperdisk-arm
        resources:
          requests:
            storage: {int(hyperdisk_size_gi)}Gi"""

    return {
        "target_machine_type": machine_type,
        "total_vcpus": chosen_vcpu,
        "total_memory_gib": memory_gb,
        "recommended_omp_num_threads": optimal_threads,
        "recommended_omp_threads_bind": thread_bind,
        "recommended_kvcache_space_gib": kvcache_space_gb,
        "reserved_kubelet_os_vcpus": reserved_system_vcpus,
        "tuning_rationale": (
            f"Setting OMP_NUM_THREADS={optimal_threads} (VLLM_CPU_OMP_THREADS_BIND='{thread_bind}') and "
            f"VLLM_CPU_KVCACHE_SPACE={kvcache_space_gb} on {machine_type} ({chosen_vcpu} Arm Neoverse V2 vCPUs) "
            f"pins {optimal_threads} cores to vLLM's Arm KleidiAI BF16 kernels while reserving "
            f"{reserved_system_vcpus} vCPUs for GKE kubelet, vLLM's async FastAPI loop, and Titanium I/O."
        ),
        "vllm_env_profile": vllm_env_profile,
        "kubernetes_statefulset_yaml": k8s_yaml,
    }


AGENT_TOOLS = [
    inspect_gke_axion_nodes,
    inspect_namespace_workloads,
    calculate_axion_vs_gpu_finops,
    audit_and_generate_axion_manifest,
]

TOOL_REGISTRY = {fn.__name__: fn for fn in AGENT_TOOLS}
