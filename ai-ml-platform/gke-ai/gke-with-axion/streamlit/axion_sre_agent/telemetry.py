"""Empirical vLLM performance telemetry, Prometheus /metrics scraper, and concurrent benchmark runner for Google Axion (C4A)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import platform
import re
import statistics
import time
from typing import Any, Dict, List, Optional
import urllib.request

# On-demand hourly reference prices (us-central1 / us-west1) for real-time $/1M token calculation
C4A_STANDARD_16_HOURLY_USD = 0.6067
C3_STANDARD_16_X86_HOURLY_USD = 0.8388
G2_STANDARD_16_L4_HOURLY_USD = 1.3560


def inspect_local_arm_cpu() -> Dict[str, Any]:
    """Reads empirical CPU architecture and Arm Neoverse V2 features from the running container."""
    arch = platform.machine()
    cpu_count = os.cpu_count() or 0
    model_name = platform.processor() or arch
    features: List[str] = []
    implementer = None
    part = None

    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            cpuinfo = f.read()
        for line in cpuinfo.splitlines():
            if ":" not in line:
                continue
            k, v = [s.strip() for s in line.split(":", 1)]
            if k.lower() in ("model name", "cpu model") and v:
                model_name = v
            elif k.lower() == "features" and not features:
                features = v.split()
            elif k.lower() == "cpu implementer" and not implementer:
                implementer = v
            elif k.lower() == "cpu part" and not part:
                part = v
    except OSError:
        pass

    bf16_supported = "bf16" in features
    sve2_supported = "sve2" in features or "sve" in features
    i8mm_supported = "i8mm" in features

    return {
        "machine_arch": arch,
        "logical_vcpus_visible": cpu_count,
        "cpu_implementer": implementer or "unknown",
        "cpu_part": part or "unknown",
        "model_name": model_name,
        "bf16_isa_detected": bf16_supported,
        "sve_isa_detected": sve2_supported,
        "i8mm_isa_detected": i8mm_supported,
        "feature_flags_sample": features[:20],
    }


def scrape_vllm_prometheus_metrics(base_url: str, timeout_sec: float = 3.0) -> Dict[str, Any]:
    """Scrapes live Prometheus metrics directly from vLLM's `/metrics` endpoint."""
    metrics_url = re.sub(r"/v1/?$", "", base_url.rstrip("/")) + "/metrics"
    try:
        req = urllib.request.Request(metrics_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw_text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return {
            "reachable": False,
            "metrics_url": metrics_url,
            "error": str(exc),
        }

    def _extract_scalar(metric_names: List[str]) -> Optional[float]:
        for name in metric_names:
            pattern = rf"^{re.escape(name)}(?:\{{[^}}]*\}})?\s+([0-9.eE+-]+)"
            match = re.search(pattern, raw_text, flags=re.MULTILINE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    ttft_sum = _extract_scalar(["vllm:time_to_first_token_seconds_sum"])
    ttft_count = _extract_scalar(["vllm:time_to_first_token_seconds_count"])
    tpot_sum = _extract_scalar(["vllm:time_per_output_token_seconds_sum"])
    tpot_count = _extract_scalar(["vllm:time_per_output_token_seconds_count"])
    e2e_sum = _extract_scalar(["vllm:e2e_request_latency_seconds_sum"])
    e2e_count = _extract_scalar(["vllm:e2e_request_latency_seconds_count"])

    prompt_tokens_total = _extract_scalar(["vllm:prompt_tokens_total", "vllm:InputTokens_total"])
    gen_tokens_total = _extract_scalar(["vllm:generation_tokens_total", "vllm:OutputTokens_total"])
    running_reqs = _extract_scalar(["vllm:num_requests_running"])
    waiting_reqs = _extract_scalar(["vllm:num_requests_waiting"])
    kv_cache_perc = _extract_scalar(["vllm:cpu_cache_usage_perc", "vllm:gpu_cache_usage_perc", "vllm:kv_cache_usage_perc"])

    avg_ttft_ms = round((ttft_sum / ttft_count) * 1000.0, 1) if ttft_sum is not None and ttft_count and ttft_count > 0 else None
    avg_tpot_ms = round((tpot_sum / tpot_count) * 1000.0, 2) if tpot_sum is not None and tpot_count and tpot_count > 0 else None
    avg_e2e_sec = round(e2e_sum / e2e_count, 2) if e2e_sum is not None and e2e_count and e2e_count > 0 else None

    return {
        "reachable": True,
        "metrics_url": metrics_url,
        "engine_avg_ttft_ms": avg_ttft_ms,
        "engine_avg_tpot_ms": avg_tpot_ms,
        "engine_avg_e2e_sec": avg_e2e_sec,
        "engine_requests_counted": int(ttft_count) if ttft_count is not None else 0,
        "prompt_tokens_total": int(prompt_tokens_total) if prompt_tokens_total is not None else 0,
        "generation_tokens_total": int(gen_tokens_total) if gen_tokens_total is not None else 0,
        "num_requests_running": int(running_reqs) if running_reqs is not None else 0,
        "num_requests_waiting": int(waiting_reqs) if waiting_reqs is not None else 0,
        "kv_cache_usage_percent": round((kv_cache_perc or 0.0) * 100.0, 2) if kv_cache_perc is not None else 0.0,
    }


def compute_cost_metrics(tokens_per_sec: float) -> Dict[str, float]:
    """Calculates empirical $/1M output tokens based on measured throughput and C4A hourly node cost."""
    if tokens_per_sec <= 0:
        return {
            "axion_usd_per_1m_tokens": 0.0,
            "x86_usd_per_1m_tokens": 0.0,
            "l4_gpu_usd_per_1m_tokens": 0.0,
        }
    tokens_per_hour = tokens_per_sec * 3600.0
    axion_per_1m = (C4A_STANDARD_16_HOURLY_USD / tokens_per_hour) * 1_000_000.0
    x86_per_1m = (C3_STANDARD_16_X86_HOURLY_USD / tokens_per_hour) * 1_000_000.0
    l4_per_1m = (G2_STANDARD_16_L4_HOURLY_USD / tokens_per_hour) * 1_000_000.0
    return {
        "axion_usd_per_1m_tokens": round(axion_per_1m, 4),
        "x86_usd_per_1m_tokens": round(x86_per_1m, 4),
        "l4_gpu_usd_per_1m_tokens": round(l4_per_1m, 4),
    }


def run_single_streaming_probe(
    base_url: str,
    model_name: str,
    prompt: str,
    max_tokens: int = 128,
    stream_id: int = 1,
) -> Dict[str, Any]:
    """Executes one streaming request against vLLM and records empirical TTFT, ITL, and decode throughput."""
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"))
    t_start = time.perf_counter()
    t_first_token: Optional[float] = None
    chunk_count = 0
    pieces: List[str] = []
    prompt_tokens = 0
    completion_tokens = 0

    stream = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": "You are a concise Kubernetes SRE assistant running on Google Axion Arm64 processors.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
        stream=True,
        stream_options={"include_usage": True},
    )

    for chunk in stream:
        usage = getattr(chunk, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or prompt_tokens
            completion_tokens = getattr(usage, "completion_tokens", 0) or completion_tokens
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            if t_first_token is None:
                t_first_token = time.perf_counter()
            chunk_count += 1
            pieces.append(chunk.choices[0].delta.content)

    t_end = time.perf_counter()
    if t_first_token is None:
        t_first_token = t_end

    text_out = "".join(pieces)
    if completion_tokens <= 0:
        completion_tokens = max(chunk_count, int(len(text_out.split()) * 1.35), 1)
    if prompt_tokens <= 0:
        prompt_tokens = max(int(len(prompt.split()) * 1.35), 1)

    ttft_ms = (t_first_token - t_start) * 1000.0
    decode_sec = max(t_end - t_first_token, 1e-6)
    e2e_sec = max(t_end - t_start, 1e-6)
    decode_tok_per_sec = completion_tokens / decode_sec if completion_tokens > 1 else completion_tokens / e2e_sec
    e2e_tok_per_sec = completion_tokens / e2e_sec
    itl_ms = (decode_sec * 1000.0) / max(completion_tokens - 1, 1)

    return {
        "stream_id": stream_id,
        "ttft_ms": round(ttft_ms, 1),
        "itl_ms_per_token": round(itl_ms, 2),
        "decode_tokens_per_sec": round(decode_tok_per_sec, 2),
        "e2e_tokens_per_sec": round(e2e_tok_per_sec, 2),
        "e2e_sec": round(e2e_sec, 2),
        "decode_sec": round(decode_sec, 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "output_preview": text_out[:180] + ("..." if len(text_out) > 180 else ""),
    }


def run_concurrent_vllm_benchmark(
    base_url: str,
    model_name: str,
    prompt: str,
    concurrency: int = 1,
    max_tokens: int = 128,
) -> Dict[str, Any]:
    """Runs `concurrency` parallel streaming requests against vLLM to measure single-stream vs batched Arm64 throughput."""
    wall_start = time.perf_counter()
    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [
            pool.submit(
                run_single_streaming_probe,
                base_url=base_url,
                model_name=model_name,
                prompt=prompt,
                max_tokens=max_tokens,
                stream_id=i + 1,
            )
            for i in range(concurrency)
        ]
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:
                errors.append(str(exc))

    wall_elapsed = max(time.perf_counter() - wall_start, 1e-6)
    results.sort(key=lambda r: r["stream_id"])

    if not results:
        return {
            "success": False,
            "concurrency": concurrency,
            "errors": errors,
        }

    total_completion_tokens = sum(r["completion_tokens"] for r in results)
    total_prompt_tokens = sum(r["prompt_tokens"] for r in results)
    aggregate_tok_per_sec = total_completion_tokens / wall_elapsed
    ttfts = [r["ttft_ms"] for r in results]
    itls = [r["itl_ms_per_token"] for r in results]
    stream_tps = [r["decode_tokens_per_sec"] for r in results]

    ttft_sorted = sorted(ttfts)
    p95_idx = min(len(ttft_sorted) - 1, int(round(0.95 * (len(ttft_sorted) - 1))))

    cost_info = compute_cost_metrics(aggregate_tok_per_sec)

    return {
        "success": True,
        "concurrency": concurrency,
        "max_tokens": max_tokens,
        "wall_elapsed_sec": round(wall_elapsed, 2),
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "aggregate_tokens_per_sec": round(aggregate_tok_per_sec, 2),
        "mean_stream_decode_tok_per_sec": round(statistics.mean(stream_tps), 2),
        "median_ttft_ms": round(statistics.median(ttfts), 1),
        "p95_ttft_ms": round(ttft_sorted[p95_idx], 1),
        "mean_itl_ms_per_token": round(statistics.mean(itls), 2),
        "streams": results,
        "errors": errors,
        **cost_info,
    }
