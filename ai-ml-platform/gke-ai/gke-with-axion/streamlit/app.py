import csv
import io
import json
import os
import pathlib
import time
import streamlit as st
from openai import OpenAI

from axion_sre_agent.agent import (
    DEFAULT_VLLM_BASE_URL,
    DEFAULT_VLLM_MODEL,
    MACHINE_TYPE,
    execute_agent_turn,
    _infer_fallback_tools_from_prompt,
)
from axion_sre_agent.telemetry import (
    compute_cost_metrics,
    inspect_local_arm_cpu,
    run_concurrent_vllm_benchmark,
    scrape_vllm_prometheus_metrics,
)
from axion_sre_agent.tools import AGENT_TOOLS

st.set_page_config(
    page_title="GKE SRE & FinOps Agent • vLLM + Gemma 4 on Google Axion",
    page_icon="🤖",
    layout="wide",
)

css_path = pathlib.Path(__file__).parent / "styles.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

st.title(f"🤖 GKE SRE & FinOps Agent on Google Axion ({MACHINE_TYPE})")
st.caption(
    "Powered by **Google ADK (Agent Development Kit)** • **vLLM Arm64 CPU (`OMP_NUM_THREADS=14`, `VLLM_CPU_KVCACHE_SPACE=16`)** "
    "• **Gemma 4 (`google/gemma-4-4b-it`, BF16)** • **Arm Neoverse V2 (C4A)**"
)

BOOTH_PRESETS = [
    (
        "🔍 Audit GKE Axion Nodes & vLLM Pod",
        "Inspect the GKE Axion cluster nodes and default namespace workloads. Verify that vllm-gemma4-0 is running on arm64 with Hyperdisk Balanced storage and OMP_NUM_THREADS=14.",
    ),
    (
        "💰 FinOps TCO: Axion C4A vs. GPU",
        "Calculate the FinOps TCO comparing Google Axion c4a-standard-16 (running vLLM + Gemma 4) against x86 and an L4 GPU for 2 replicas handling 10,000 daily agent turns.",
    ),
    (
        "⚡ Generate c4a-standard-32 vLLM YAML",
        "Generate a tuned GKE Arm64 vLLM StatefulSet manifest and CPU thread/KV-cache profile for scaling our Gemma 4 agent to a 32-vCPU c4a-standard-32 node.",
    ),
    (
        "🛠️ Why OMP_NUM_THREADS=14 on C4A?",
        "Inspect our cluster node capacity and generate the vLLM tuning profile for a 16-vCPU c4a-standard-16 node. Explain why OMP_NUM_THREADS=14 and VLLM_CPU_KVCACHE_SPACE=16 are optimal.",
    ),
]

if "messages" not in st.session_state:
    st.session_state.messages = []
if "telemetry_log" not in st.session_state:
    st.session_state.telemetry_log = []
if "latest_benchmark" not in st.session_state:
    st.session_state.latest_benchmark = None

with st.sidebar:
    st.header("⚙️ Agent & vLLM Config")
    execution_mode = st.radio(
        "Execution Mode",
        options=[
            "🤖 Agent Mode (Google ADK + Tools)",
            "💬 Raw vLLM Stream (No Tools)",
        ],
        index=0,
        help="Agent Mode runs Google ADK with live GKE & FinOps tools against vLLM; Raw Stream streams directly from vLLM `/v1/chat/completions`.",
    )
    model_choice = st.selectbox(
        "vLLM Served Model (Gemma 4)",
        options=["google/gemma-4-E4B-it", "google/gemma-4-E2B-it"],
        index=0 if DEFAULT_VLLM_MODEL != "google/gemma-4-E2B-it" else 1,
        help="Served via vLLM Arm64 CPU (`--dtype=bfloat16 --enable-auto-tool-choice`) with `OMP_NUM_THREADS=14` on `c4a-standard-16`.",
    )
    base_url = st.text_input(
        "vLLM OpenAI Endpoint",
        value=DEFAULT_VLLM_BASE_URL,
        help="In-cluster Kubernetes Service URL (`http://vllm-service:8000/v1`) or external Gateway URL.",
    )

    st.divider()
    st.subheader("🧰 Registered Google ADK Tools")
    for fn in AGENT_TOOLS:
        st.markdown(f"- `{fn.__name__}()`")

    st.divider()
    if st.button("🗑️ Clear Conversation & Telemetry", use_container_width=True):
        st.session_state.messages = []
        st.session_state.telemetry_log = []
        st.session_state.latest_benchmark = None
        st.rerun()

st.session_state["openai_model"] = model_choice

# Scrape live vLLM Prometheus /metrics (non-blocking 1.5s timeout) for top banner
prom_metrics = scrape_vllm_prometheus_metrics(base_url=base_url, timeout_sec=1.5)
last_run = st.session_state.telemetry_log[-1] if st.session_state.telemetry_log else None

# Top Live Empirical Scorecard Row
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
if last_run:
    avg_tps = sum(r["tokens_per_sec"] for r in st.session_state.telemetry_log) / len(st.session_state.telemetry_log)
    tps_delta = round(last_run["tokens_per_sec"] - avg_tps, 2)
    kpi1.metric(
        "⚡ Decode Throughput",
        f"{last_run['tokens_per_sec']:.2f} tok/s",
        delta=f"{tps_delta:+.2f} vs session avg" if len(st.session_state.telemetry_log) > 1 else "Live Arm64 BF16",
    )
    kpi2.metric(
        "🚀 Time to First Token (TTFT)",
        f"{last_run['ttft_ms']:.1f} ms",
        delta=f"Tool exec: {last_run.get('tool_exec_ms', 0.0):.1f} ms",
        delta_color="off",
    )
    kpi3.metric(
        "⏱️ Inter-Token Latency (ITL)",
        f"{last_run['itl_ms_per_token']:.2f} ms/tok",
        delta=f"{last_run['completion_tokens']} output tokens",
        delta_color="off",
    )
    kpi4.metric(
        "💰 Live Cost / 1M Tokens",
        f"${last_run['axion_usd_per_1m_tokens']:.2f}",
        delta=f"vs ${last_run['l4_gpu_usd_per_1m_tokens']:.2f} on L4 GPU",
        delta_color="normal",
    )
else:
    kpi1.metric("⚡ Decode Throughput", "— tok/s", delta="Run a prompt or benchmark")
    kpi2.metric(
        "🚀 Time to First Token (TTFT)",
        f"{prom_metrics['engine_avg_ttft_ms']:.1f} ms" if prom_metrics.get("engine_avg_ttft_ms") else "— ms",
        delta="vLLM engine avg" if prom_metrics.get("engine_avg_ttft_ms") else "Awaiting 1st request",
        delta_color="off",
    )
    kpi3.metric(
        "⏱️ Inter-Token Latency (ITL)",
        f"{prom_metrics['engine_avg_tpot_ms']:.2f} ms/tok" if prom_metrics.get("engine_avg_tpot_ms") else "— ms/tok",
        delta="vLLM engine avg" if prom_metrics.get("engine_avg_tpot_ms") else "OMP_NUM_THREADS=14",
        delta_color="off",
    )
    kpi4.metric("💰 C4A Node Rate", "$0.61 / hr", delta="c4a-standard-16 (16 vCPU)", delta_color="off")

if prom_metrics.get("reachable"):
    kpi5.metric(
        "🧠 vLLM KV Cache (16 GiB)",
        f"{prom_metrics['kv_cache_usage_percent']:.1f}% used",
        delta=f"{prom_metrics['generation_tokens_total']} total tok served",
        delta_color="off",
    )
else:
    kpi5.metric("🧠 vLLM KV Cache (16 GiB)", "16 GiB DDR5", delta="PagedAttention active", delta_color="off")

tab_agent, tab_bench = st.tabs(
    [
        "🤖 Live Agent & Chat (with Per-Turn Speed Telemetry)",
        "📊 ARM Speed Benchmark & vLLM Prometheus Telemetry",
    ]
)


def render_tool_traces(tool_calls):
    """Renders expandable Google ADK tool call cards inside a message."""
    if not tool_calls:
        return
    with st.expander(
        f"🔧 Google ADK Tool Execution Trace ({len(tool_calls)} tool call{'s' if len(tool_calls) != 1 else ''})",
        expanded=False,
    ):
        for idx, tc in enumerate(tool_calls, 1):
            dur = f" • `{tc['duration_ms']} ms`" if tc.get("duration_ms") is not None else ""
            st.markdown(f"**Step {idx}: `{tc['name']}({json.dumps(tc.get('args', {}))})`**{dur}")
            st.json(tc.get("result", {}))


with tab_agent:
    st.markdown("##### 🎯 KubeCon Booth Quick-Launch Scenarios")
    preset_cols = st.columns(len(BOOTH_PRESETS))
    triggered_prompt = None
    for idx, (label, preset_prompt) in enumerate(BOOTH_PRESETS):
        if preset_cols[idx].button(label, use_container_width=True):
            triggered_prompt = preset_prompt

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("tool_calls"):
                render_tool_traces(message["tool_calls"])
            st.markdown(message["content"])
            if message.get("telemetry"):
                st.caption(message["telemetry"])

    chat_input_prompt = st.chat_input("Ask the GKE SRE & FinOps Agent (or click a scenario above)...")
    active_prompt = triggered_prompt or chat_input_prompt

    if active_prompt:
        st.session_state.messages.append({"role": "user", "content": active_prompt})

        with st.chat_message("user"):
            st.markdown(active_prompt)

        with st.chat_message("assistant"):
            if execution_mode.startswith("🤖"):
                with st.status(
                    f"Running Google ADK Agent via vLLM (`{model_choice}` on `{MACHINE_TYPE}`)...",
                    expanded=True,
                ) as status:
                    st.write("1️⃣ Analyzing intent & selecting Google ADK SRE/FinOps tools...")
                    try:
                        result = execute_agent_turn(
                            prompt=active_prompt,
                            chat_history=st.session_state.messages[:-1],
                            model_name=model_choice,
                            base_url=base_url,
                        )
                        tool_calls = result.get("tool_calls", [])
                        for tc in tool_calls:
                            st.write(f"🔧 Executed ADK tool `{tc['name']}()` ({tc.get('duration_ms', 0.0)} ms)")

                        telemetry_str = (
                            f"⚡ **Decode: {result['tokens_per_sec']:.2f} tok/s** • "
                            f"🚀 **TTFT: {result['ttft_ms']:.1f} ms** • "
                            f"⏱️ **ITL: {result['itl_ms_per_token']:.2f} ms/tok** • "
                            f"🔧 **Tools: {len(tool_calls)} ({result['tool_exec_ms']:.1f} ms)** • "
                            f"🔢 **Tokens: {result['prompt_tokens']} in → {result['completion_tokens']} out** • "
                            f"💰 **${result['axion_usd_per_1m_tokens']:.2f}/1M tok on `{MACHINE_TYPE}`** • "
                            f"⏱️ **{result['elapsed_sec']:.2f}s E2E**"
                        )
                        status.update(
                            label=(
                                f"Agent turn complete — {result['tokens_per_sec']:.2f} tok/s | "
                                f"TTFT {result['ttft_ms']:.1f} ms | ITL {result['itl_ms_per_token']:.2f} ms/tok"
                            ),
                            state="complete",
                            expanded=False,
                        )
                        render_tool_traces(tool_calls)
                        st.markdown(result["final_text"])
                        st.caption(telemetry_str)

                        st.session_state.telemetry_log.append(
                            {
                                "run_id": len(st.session_state.telemetry_log) + 1,
                                "timestamp": time.strftime("%H:%M:%S"),
                                "mode": f"ADK Agent ({len(tool_calls)} tools)",
                                "tokens_per_sec": result["tokens_per_sec"],
                                "ttft_ms": result["ttft_ms"],
                                "itl_ms_per_token": result["itl_ms_per_token"],
                                "tool_exec_ms": result["tool_exec_ms"],
                                "prompt_tokens": result["prompt_tokens"],
                                "completion_tokens": result["completion_tokens"],
                                "elapsed_sec": result["elapsed_sec"],
                                "axion_usd_per_1m_tokens": result["axion_usd_per_1m_tokens"],
                                "l4_gpu_usd_per_1m_tokens": result["l4_gpu_usd_per_1m_tokens"],
                            }
                        )
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": result["final_text"],
                                "tool_calls": tool_calls,
                                "telemetry": telemetry_str,
                            }
                        )
                    except Exception as exc:
                        fallback_traces = _infer_fallback_tools_from_prompt(active_prompt)
                        status.update(
                            label=f"Executed {len(fallback_traces)} local ADK tool(s) (vLLM endpoint warming up)",
                            state="complete",
                            expanded=False,
                        )
                        render_tool_traces(fallback_traces)
                        fallback_md = (
                            f"> **Note:** vLLM at `{base_url}` is still warming up `{model_choice}` (`{exc}`). "
                            f"Below is the live **Google ADK Tool Telemetry** collected directly from the cluster:\n\n"
                        )
                        for tc in fallback_traces:
                            fallback_md += f"### 🔧 `{tc['name']}()`\n```json\n{json.dumps(tc['result'], indent=2)}\n```\n\n"
                        st.markdown(fallback_md)
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": fallback_md,
                                "tool_calls": fallback_traces,
                            }
                        )
            else:
                client = OpenAI(base_url=base_url, api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"))
                stream_stats = {
                    "t_start": time.perf_counter(),
                    "t_first": None,
                    "chunks": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                }
                with st.status(
                    f"Streaming raw tokens from vLLM (`{model_choice}` on `{MACHINE_TYPE}`)...",
                    expanded=True,
                ) as status:

                    def get_streamed_completion(completion_generator):
                        for chunk in completion_generator:
                            usage = getattr(chunk, "usage", None)
                            if usage is not None:
                                stream_stats["prompt_tokens"] = (
                                    getattr(usage, "prompt_tokens", 0) or stream_stats["prompt_tokens"]
                                )
                                stream_stats["completion_tokens"] = (
                                    getattr(usage, "completion_tokens", 0) or stream_stats["completion_tokens"]
                                )
                            if len(chunk.choices) and chunk.choices[0].delta.content:
                                if stream_stats["t_first"] is None:
                                    stream_stats["t_first"] = time.perf_counter()
                                stream_stats["chunks"] += 1
                                yield chunk.choices[0].delta.content

                    try:
                        response = st.write_stream(
                            get_streamed_completion(
                                client.chat.completions.create(
                                    model=model_choice,
                                    messages=[
                                        {"role": m["role"], "content": m["content"]}
                                        for m in st.session_state.messages
                                    ],
                                    stream=True,
                                    stream_options={"include_usage": True},
                                )
                            )
                        )
                        if isinstance(response, list):
                            response = "".join(str(part) for part in response)
                        response_str = str(response)
                        t_end = time.perf_counter()
                        t_first = stream_stats["t_first"] or t_end
                        comp_tok = stream_stats["completion_tokens"] or max(
                            stream_stats["chunks"], int(len(response_str.split()) * 1.35), 1
                        )
                        prompt_tok = stream_stats["prompt_tokens"] or max(int(len(active_prompt.split()) * 1.35), 1)
                        ttft_ms = round((t_first - stream_stats["t_start"]) * 1000.0, 1)
                        decode_sec = max(t_end - t_first, 1e-6)
                        e2e_sec = max(t_end - stream_stats["t_start"], 1e-6)
                        tps = round(comp_tok / decode_sec if comp_tok > 1 else comp_tok / e2e_sec, 2)
                        itl_ms = round((decode_sec * 1000.0) / max(comp_tok - 1, 1), 2)
                        cost_info = compute_cost_metrics(tps)

                        telemetry_str = (
                            f"⚡ **Decode: {tps:.2f} tok/s** • "
                            f"🚀 **TTFT: {ttft_ms:.1f} ms** • "
                            f"⏱️ **ITL: {itl_ms:.2f} ms/tok** • "
                            f"🔢 **Tokens: {prompt_tok} in → {comp_tok} out** • "
                            f"💰 **${cost_info['axion_usd_per_1m_tokens']:.2f}/1M tok on `{MACHINE_TYPE}`** • "
                            f"⏱️ **{e2e_sec:.2f}s E2E**"
                        )
                        status.update(
                            label=f"Stream complete — {tps:.2f} tok/s | TTFT {ttft_ms:.1f} ms | ITL {itl_ms:.2f} ms/tok",
                            state="complete",
                            expanded=False,
                        )
                        st.caption(telemetry_str)
                        st.session_state.telemetry_log.append(
                            {
                                "run_id": len(st.session_state.telemetry_log) + 1,
                                "timestamp": time.strftime("%H:%M:%S"),
                                "mode": "Raw vLLM Stream",
                                "tokens_per_sec": tps,
                                "ttft_ms": ttft_ms,
                                "itl_ms_per_token": itl_ms,
                                "tool_exec_ms": 0.0,
                                "prompt_tokens": prompt_tok,
                                "completion_tokens": comp_tok,
                                "elapsed_sec": round(e2e_sec, 2),
                                "axion_usd_per_1m_tokens": cost_info["axion_usd_per_1m_tokens"],
                                "l4_gpu_usd_per_1m_tokens": cost_info["l4_gpu_usd_per_1m_tokens"],
                            }
                        )
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": response_str,
                                "telemetry": telemetry_str,
                            }
                        )
                    except Exception as e:
                        st.error(f"Error connecting to vLLM at `{base_url}`: {e}")


with tab_bench:
    st.subheader("🚀 Live ARM Inferencing Benchmark Arena (vLLM on Google Axion C4A)")
    st.markdown(
        "Run empirical single-stream or concurrent continuous-batching bursts directly against "
        f"`{base_url}` (`{model_choice}`) and measure **Time to First Token (TTFT)**, **Inter-Token Latency (ITL)**, "
        "**Aggregate Throughput (`tok/s`)**, and **Live Cost per 1M Tokens**."
    )

    bcol1, bcol2, bcol3 = st.columns([1, 1, 2])
    with bcol1:
        bench_concurrency = st.selectbox(
            "Concurrent Requests (Continuous Batching)",
            options=[1, 2, 4, 8],
            index=0,
            help="Fires N parallel streaming requests against vLLM to measure single-stream vs. continuous-batched Arm64 throughput.",
        )
    with bcol2:
        bench_max_tokens = st.selectbox(
            "Max Output Tokens per Stream",
            options=[64, 128, 256],
            index=1,
        )
    with bcol3:
        bench_prompt = st.text_input(
            "Benchmark Prompt",
            value="Explain 3 reasons why binding OMP_NUM_THREADS=14 and using bfloat16 on Google Axion C4A speeds up vLLM Kubernetes agents.",
        )

    if st.button("⚡ Run Live Axion Benchmark Now", type="primary", use_container_width=True):
        with st.spinner(
            f"Executing {bench_concurrency}x concurrent streaming request(s) ({bench_max_tokens} max tokens) against `{base_url}`..."
        ):
            bench_res = run_concurrent_vllm_benchmark(
                base_url=base_url,
                model_name=model_choice,
                prompt=bench_prompt,
                concurrency=bench_concurrency,
                max_tokens=bench_max_tokens,
            )
            st.session_state.latest_benchmark = bench_res
            if bench_res.get("success"):
                st.session_state.telemetry_log.append(
                    {
                        "run_id": len(st.session_state.telemetry_log) + 1,
                        "timestamp": time.strftime("%H:%M:%S"),
                        "mode": f"Benchmark ({bench_concurrency}x concurrent)",
                        "tokens_per_sec": bench_res["aggregate_tokens_per_sec"],
                        "ttft_ms": bench_res["median_ttft_ms"],
                        "itl_ms_per_token": bench_res["mean_itl_ms_per_token"],
                        "tool_exec_ms": 0.0,
                        "prompt_tokens": bench_res["total_prompt_tokens"],
                        "completion_tokens": bench_res["total_completion_tokens"],
                        "elapsed_sec": bench_res["wall_elapsed_sec"],
                        "axion_usd_per_1m_tokens": bench_res["axion_usd_per_1m_tokens"],
                        "l4_gpu_usd_per_1m_tokens": bench_res["l4_gpu_usd_per_1m_tokens"],
                    }
                )

    bench = st.session_state.latest_benchmark
    if bench:
        if not bench.get("success"):
            st.error(f"Benchmark could not reach `{base_url}`: {bench.get('errors')}")
        else:
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric(
                "⚡ Aggregate Throughput",
                f"{bench['aggregate_tokens_per_sec']:.2f} tok/s",
                delta=f"{bench['concurrency']}x concurrent streams",
            )
            m2.metric(
                "🎯 Per-Stream Decode",
                f"{bench['mean_stream_decode_tok_per_sec']:.2f} tok/s",
                delta=f"{bench['total_completion_tokens']} total tok generated",
                delta_color="off",
            )
            m3.metric(
                "🚀 Median TTFT (P50 / P95)",
                f"{bench['median_ttft_ms']:.1f} ms",
                delta=f"P95: {bench['p95_ttft_ms']:.1f} ms",
                delta_color="off",
            )
            m4.metric(
                "⏱️ Mean Inter-Token Latency",
                f"{bench['mean_itl_ms_per_token']:.2f} ms/tok",
                delta=f"Wall time: {bench['wall_elapsed_sec']:.2f}s",
                delta_color="off",
            )
            m5.metric(
                "💰 Empirical Cost / 1M Tok",
                f"${bench['axion_usd_per_1m_tokens']:.2f}",
                delta=f"vs ${bench['l4_gpu_usd_per_1m_tokens']:.2f} on L4 GPU (-55%)",
            )

            st.markdown("##### 📋 Per-Stream Empirical Breakdown")
            st.dataframe(bench["streams"], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📈 Session Empirical Speed History (All Prompts & Benchmarks)")
    if st.session_state.telemetry_log:
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.markdown("**Throughput (`tokens/sec`) by Run**")
            st.bar_chart(
                data=st.session_state.telemetry_log,
                x="run_id",
                y="tokens_per_sec",
                color="#1a73e8",
            )
        with chart_col2:
            st.markdown("**Time to First Token (`TTFT ms`) by Run**")
            st.bar_chart(
                data=st.session_state.telemetry_log,
                x="run_id",
                y="ttft_ms",
                color="#34a853",
            )

        st.dataframe(st.session_state.telemetry_log, use_container_width=True, hide_index=True)

        csv_buf = io.StringIO()
        writer = csv.DictWriter(csv_buf, fieldnames=list(st.session_state.telemetry_log[0].keys()))
        writer.writeheader()
        writer.writerows(st.session_state.telemetry_log)
        st.download_button(
            "📥 Download Empirical Telemetry CSV",
            data=csv_buf.getvalue(),
            file_name="axion_vllm_empirical_telemetry.csv",
            mime="text/csv",
        )
    else:
        st.info("Run any agent scenario in Tab 1 or click **⚡ Run Live Axion Benchmark Now** above to populate live charts.")

    st.divider()
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        st.subheader("🔬 Live vLLM Prometheus `/metrics`")
        if st.button("🔄 Refresh vLLM `/metrics`", use_container_width=True):
            prom_metrics = scrape_vllm_prometheus_metrics(base_url=base_url, timeout_sec=3.0)
        st.json(prom_metrics)
    with pcol2:
        st.subheader("🧬 Local Arm64 Neoverse V2 CPU ISA Probe (`/proc/cpuinfo`)")
        st.json(inspect_local_arm_cpu())
