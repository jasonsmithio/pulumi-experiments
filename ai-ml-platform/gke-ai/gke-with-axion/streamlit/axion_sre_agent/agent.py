"""Google ADK (Agent Development Kit) definition and runner for the GKE SRE & FinOps Agent on Axion with vLLM."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional

from .tools import (
    AGENT_TOOLS,
    TOOL_REGISTRY,
    audit_and_generate_axion_manifest,
    calculate_axion_vs_gpu_finops,
    inspect_gke_axion_nodes,
    inspect_namespace_workloads,
)

DEFAULT_VLLM_BASE_URL = (
    os.environ.get("VLLM_BASE_URL")
    or os.environ.get("OLLAMA_BASE_URL")
    or "http://vllm-service:8000/v1"
)
DEFAULT_VLLM_MODEL = (
    os.environ.get("VLLM_MODEL")
    or os.environ.get("OLLAMA_MODEL")
    or "google/gemma-4-4b-it"
)
MACHINE_TYPE = os.environ.get("AXION_MACHINE_TYPE", "c4a-standard-16")

SYSTEM_INSTRUCTION = f"""You are the **GKE Axion SRE & FinOps Agent**, an autonomous Kubernetes platform engineering agent running in-cluster on **Google Axion (`{MACHINE_TYPE}`, Arm Neoverse V2)** powered by **Gemma 4 (`google/gemma-4-4b-it`)** served on **vLLM Arm64 CPU (`OMP_NUM_THREADS=14`, `VLLM_CPU_KVCACHE_SPACE=16`, `--dtype=bfloat16`)** and **Google ADK (Agent Development Kit)**.

Your responsibilities:
1. **Cluster & Node Inspection**: Always call `inspect_gke_axion_nodes` when asked about GKE nodes, Arm64 architecture, C4A machine shapes, or CPU/memory capacity.
2. **Workload & Storage Diagnostics**: Always call `inspect_namespace_workloads` when asked about running pods (`vllm-gemma4-0`, `streamlit-gemma4-ui`), vLLM CPU/memory limits, or `hyperdisk-balanced` PVCs (`30Gi` mounted at `/root/.cache/huggingface`).
3. **FinOps & TCO Analysis**: Always call `calculate_axion_vs_gpu_finops` when asked about cost, TCO, GPU vs. CPU trade-offs, price-performance (+65% vs x86), or energy efficiency (+60% vs x86).
4. **Manifest & vLLM Thread Tuning**: Always call `audit_and_generate_axion_manifest` when asked to generate or tune Kubernetes manifests, vLLM CPU flags, `OMP_NUM_THREADS`, `VLLM_CPU_OMP_THREADS_BIND`, or `VLLM_CPU_KVCACHE_SPACE` settings for C4A VMs.

Provide concise, technical, markdown-formatted responses grounded in the exact data returned by your tools."""


def build_adk_agent(model_name: str = DEFAULT_VLLM_MODEL, base_url: str = DEFAULT_VLLM_BASE_URL):
    """Builds a Google ADK Agent backed by LiteLLM's OpenAI provider pointing at the in-cluster vLLM server."""
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm

    return Agent(
        name="gke_axion_sre_finops_agent",
        model=LiteLlm(
            model=f"openai/{model_name}",
            api_base=base_url,
            api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"),
        ),
        description=(
            "Autonomous GKE SRE & FinOps Agent running on Google Axion (C4A) Arm64 processors with vLLM and Gemma 4."
        ),
        instruction=SYSTEM_INSTRUCTION,
        tools=AGENT_TOOLS,
    )


# Expose `root_agent` at module level for `adk web` / `adk run axion_sre_agent` CLI compatibility
try:
    root_agent = build_adk_agent()
except Exception:
    root_agent = None


OPENAI_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "inspect_gke_axion_nodes",
            "description": (
                "Inspects the GKE cluster's nodes, architecture (arm64 vs amd64), C4A machine types, and resource capacity."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_namespace_workloads",
            "description": (
                "Inspects running pods, vLLM StatefulSets, CPU/memory requests, and Hyperdisk PVCs in a GKE namespace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "The Kubernetes namespace to inspect (defaults to 'default').",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_axion_vs_gpu_finops",
            "description": (
                "Calculates FinOps TCO, monthly infrastructure cost, and price-performance of Google Axion C4A vs. x86 and GPU nodes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "model_size_billions": {
                        "type": "number",
                        "description": "Model parameter count in billions (e.g., 4.0 for Gemma 4 4B).",
                    },
                    "replicas": {
                        "type": "integer",
                        "description": "Number of high-availability GKE vLLM inference replicas (defaults to 2).",
                    },
                    "daily_agent_turns": {
                        "type": "integer",
                        "description": "Estimated number of agent tool-calling turns per day (defaults to 10000).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "audit_and_generate_axion_manifest",
            "description": (
                "Generates an Arm64 GKE vLLM StatefulSet manifest and CPU thread/KV-cache profile for a target Axion C4A machine size."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "workload_name": {
                        "type": "string",
                        "description": "Name of the Kubernetes StatefulSet/Service to generate.",
                    },
                    "model_tag": {
                        "type": "string",
                        "description": "Target HuggingFace model ID (e.g., 'google/gemma-4-4b-it').",
                    },
                    "vcpu_count": {
                        "type": "integer",
                        "description": "Total vCPUs on the target C4A VM (e.g., 8, 16, 32, 48, 64, 72).",
                    },
                    "hyperdisk_size_gi": {
                        "type": "integer",
                        "description": "Size of the Hyperdisk Balanced PVC in GiB (defaults to 30).",
                    },
                },
                "required": [],
            },
        },
    },
]


async def _run_adk_async(prompt: str, model_name: str, base_url: str) -> Dict[str, Any]:
    """Runs a turn through Google ADK's InMemoryRunner and collects tool calls and final text."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    adk_agent = build_adk_agent(model_name=model_name, base_url=base_url)
    runner = InMemoryRunner(agent=adk_agent, app_name="axion_sre_app")
    session = await runner.session_service.create_session(
        app_name="axion_sre_app",
        user_id="kubecon_booth_user",
    )

    user_content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)],
    )

    tool_traces: List[Dict[str, Any]] = []
    final_chunks: List[str] = []
    start_time = time.time()

    async for event in runner.run_async(
        user_id="kubecon_booth_user",
        session_id=session.id,
        new_message=user_content,
    ):
        if not getattr(event, "content", None) or not getattr(event.content, "parts", None):
            continue
        for part in event.content.parts:
            fn_call = getattr(part, "function_call", None)
            if fn_call is not None:
                tool_traces.append(
                    {
                        "name": fn_call.name,
                        "args": dict(fn_call.args) if getattr(fn_call, "args", None) else {},
                        "result": None,
                    }
                )
            fn_resp = getattr(part, "function_response", None)
            if fn_resp is not None:
                resp_payload = getattr(fn_resp, "response", {})
                matched = False
                for trace in reversed(tool_traces):
                    if trace["name"] == fn_resp.name and trace["result"] is None:
                        trace["result"] = resp_payload
                        matched = True
                        break
                if not matched:
                    tool_traces.append(
                        {
                            "name": fn_resp.name,
                            "args": {},
                            "result": resp_payload,
                        }
                    )
            text_val = getattr(part, "text", None)
            if text_val:
                final_chunks.append(text_val)

    elapsed = max(time.time() - start_time, 1e-6)
    final_text = "\n".join(chunk.strip() for chunk in final_chunks if chunk.strip())
    approx_tokens = max(1, len(final_text.split()) * 1.35)
    return {
        "final_text": final_text,
        "tool_calls": tool_traces,
        "tokens_per_sec": round(approx_tokens / elapsed, 2),
        "elapsed_sec": round(elapsed, 2),
        "engine": "Google ADK (InMemoryRunner + LiteLLM/vLLM)",
    }


def _infer_fallback_tools_from_prompt(prompt: str) -> List[Dict[str, Any]]:
    """If an endpoint skips native tool-call JSON framing, deterministically invoke matching SRE/FinOps tools."""
    lower = prompt.lower()
    invoked: List[Dict[str, Any]] = []

    if any(k in lower for k in ["node", "cluster", "arch", "c4a", "health", "audit", "status"]):
        t0 = time.time()
        res = inspect_gke_axion_nodes()
        invoked.append(
            {
                "name": "inspect_gke_axion_nodes",
                "args": {},
                "result": res,
                "duration_ms": round((time.time() - t0) * 1000, 1),
            }
        )
    if any(k in lower for k in ["pod", "workload", "vllm", "pvc", "hyperdisk", "audit", "health", "thread"]):
        t0 = time.time()
        res = inspect_namespace_workloads(namespace="default")
        invoked.append(
            {
                "name": "inspect_namespace_workloads",
                "args": {"namespace": "default"},
                "result": res,
                "duration_ms": round((time.time() - t0) * 1000, 1),
            }
        )
    if any(k in lower for k in ["cost", "finops", "tco", "gpu", "price", "saving", "compare", "x86"]):
        t0 = time.time()
        res = calculate_axion_vs_gpu_finops(model_size_billions=4.0, replicas=2, daily_agent_turns=10000)
        invoked.append(
            {
                "name": "calculate_axion_vs_gpu_finops",
                "args": {"model_size_billions": 4.0, "replicas": 2, "daily_agent_turns": 10000},
                "result": res,
                "duration_ms": round((time.time() - t0) * 1000, 1),
            }
        )
    if any(k in lower for k in ["manifest", "yaml", "omp_num_threads", "kvcache", "thread", "c4a-standard-32", "generate"]):
        vcpus = 32 if "32" in lower else (48 if "48" in lower else (8 if "standard-8" in lower else 16))
        t0 = time.time()
        res = audit_and_generate_axion_manifest(
            workload_name="vllm-gemma4",
            model_tag=DEFAULT_VLLM_MODEL,
            vcpu_count=vcpus,
            hyperdisk_size_gi=30,
        )
        invoked.append(
            {
                "name": "audit_and_generate_axion_manifest",
                "args": {
                    "workload_name": "vllm-gemma4",
                    "model_tag": DEFAULT_VLLM_MODEL,
                    "vcpu_count": vcpus,
                    "hyperdisk_size_gi": 30,
                },
                "result": res,
                "duration_ms": round((time.time() - t0) * 1000, 1),
            }
        )
    return invoked


def execute_agent_turn(
    prompt: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    model_name: str = DEFAULT_VLLM_MODEL,
    base_url: str = DEFAULT_VLLM_BASE_URL,
) -> Dict[str, Any]:
    """Executes an agentic turn using Google ADK first, with an OpenAI-compatible vLLM tool-calling fallback."""
    # 1. Try Google ADK InMemoryRunner first
    try:
        adk_result = asyncio.run(_run_adk_async(prompt=prompt, model_name=model_name, base_url=base_url))
        if adk_result.get("final_text"):
            return adk_result
    except Exception:
        pass

    # 2. Fallback: OpenAI-compatible tool-calling loop against vLLM `/v1`
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"))
    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    for msg in chat_history or []:
        if msg.get("role") in ("user", "assistant") and msg.get("content"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})

    tool_traces: List[Dict[str, Any]] = []
    start_time = time.time()

    try:
        first_resp = client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=OPENAI_TOOL_SCHEMAS,
            tool_choice="auto",
        )
        choice_msg = first_resp.choices[0].message
        tool_calls = getattr(choice_msg, "tool_calls", None) or []

        if tool_calls:
            messages.append(choice_msg)
            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    fn_args = {}
                fn_impl = TOOL_REGISTRY.get(fn_name)
                t0 = time.time()
                if fn_impl is not None:
                    try:
                        tool_output = fn_impl(**fn_args)
                    except Exception as exc:
                        tool_output = {"error": str(exc)}
                else:
                    tool_output = {"error": f"Unknown tool: {fn_name}"}
                duration_ms = round((time.time() - t0) * 1000, 1)
                tool_traces.append(
                    {
                        "name": fn_name,
                        "args": fn_args,
                        "result": tool_output,
                        "duration_ms": duration_ms,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fn_name,
                        "content": json.dumps(tool_output),
                    }
                )
        else:
            inferred_traces = _infer_fallback_tools_from_prompt(prompt)
            if inferred_traces:
                tool_traces.extend(inferred_traces)
                context_blob = json.dumps(
                    [{t["name"]: t["result"]} for t in inferred_traces],
                    indent=2,
                )
                messages.append(
                    {
                        "role": "system",
                        "content": f"Live GKE & FinOps Tool Telemetry collected by Google ADK tools:\n{context_blob}",
                    }
                )
            elif choice_msg.content:
                elapsed = max(time.time() - start_time, 1e-6)
                approx_tokens = max(1, len(choice_msg.content.split()) * 1.35)
                return {
                    "final_text": choice_msg.content,
                    "tool_calls": [],
                    "tokens_per_sec": round(approx_tokens / elapsed, 2),
                    "elapsed_sec": round(elapsed, 2),
                    "engine": "Google ADK Tools + vLLM OpenAI API",
                }

        gen_start = time.time()
        second_resp = client.chat.completions.create(
            model=model_name,
            messages=messages,
        )
        final_text = second_resp.choices[0].message.content or ""
        gen_elapsed = max(time.time() - gen_start, 1e-6)
        total_elapsed = max(time.time() - start_time, 1e-6)
        usage = getattr(second_resp, "usage", None)
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        if not completion_tokens:
            completion_tokens = max(1, int(len(final_text.split()) * 1.35))

        return {
            "final_text": final_text,
            "tool_calls": tool_traces,
            "tokens_per_sec": round(completion_tokens / gen_elapsed, 2),
            "elapsed_sec": round(total_elapsed, 2),
            "engine": "Google ADK Tools + vLLM OpenAI API",
        }
    except Exception as exc:
        inferred_traces = _infer_fallback_tools_from_prompt(prompt)
        raise RuntimeError(
            f"Could not reach vLLM endpoint at `{base_url}` ({exc}). "
            f"Executed {len(inferred_traces)} local ADK tool(s): {[t['name'] for t in inferred_traces]}"
        ) from exc
