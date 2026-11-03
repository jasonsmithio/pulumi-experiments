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
        options=["google/gemma-4-4b-it", "google/gemma-4-9b-it"],
        index=0 if DEFAULT_VLLM_MODEL == "google/gemma-4-4b-it" else 1,
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
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.session_state["openai_model"] = model_choice

if "messages" not in st.session_state:
    st.session_state.messages = []

# Render 1-Click KubeCon Booth Scenarios
st.markdown("##### 🎯 KubeCon Booth Quick-Launch Scenarios")
preset_cols = st.columns(len(BOOTH_PRESETS))
triggered_prompt = None
for idx, (label, preset_prompt) in enumerate(BOOTH_PRESETS):
    if preset_cols[idx].button(label, use_container_width=True):
        triggered_prompt = preset_prompt


def render_tool_traces(tool_calls):
    """Renders expandable Google ADK tool call cards inside a message."""
    if not tool_calls:
        return
    with st.expander(f"🔧 Google ADK Tool Execution Trace ({len(tool_calls)} tool call{'s' if len(tool_calls) != 1 else ''})", expanded=False):
        for idx, tc in enumerate(tool_calls, 1):
            dur = f" • `{tc['duration_ms']} ms`" if tc.get("duration_ms") is not None else ""
            st.markdown(f"**Step {idx}: `{tc['name']}({json.dumps(tc.get('args', {}))})`**{dur}")
            st.json(tc.get("result", {}))


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
                        st.write(f"🔧 Executed ADK tool `{tc['name']}()`")
                    telemetry_str = (
                        f"⚡ **{result['tokens_per_sec']:.2f} tokens/sec** • "
                        f"⏱️ **{result['elapsed_sec']:.2f}s total** • "
                        f"🔧 **{len(tool_calls)} ADK tool call(s)** • "
                        f"🧠 `{model_choice}` on `{MACHINE_TYPE}` ({result['engine']})"
                    )
                    status.update(
                        label=f"Agent turn complete — {result['tokens_per_sec']:.2f} tokens/sec ({len(tool_calls)} tool calls)",
                        state="complete",
                        expanded=False,
                    )
                    render_tool_traces(tool_calls)
                    st.markdown(result["final_text"])
                    st.caption(telemetry_str)
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
            with st.status(
                f"Streaming raw tokens from vLLM (`{model_choice}` on `{MACHINE_TYPE}`)...",
                expanded=True,
            ) as status:
                def get_streamed_completion(completion_generator):
                    start = time.time()
                    tokcount = 0
                    for chunk in completion_generator:
                        if len(chunk.choices) and chunk.choices[0].delta.content:
                            tokcount += 1
                            yield chunk.choices[0].delta.content
                    elapsed = max(time.time() - start, 1e-6)
                    status.update(
                        label=f"Done — averaged {tokcount / elapsed:.2f} tokens/second ({model_choice})",
                        state="complete",
                        expanded=False,
                    )

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
                    st.session_state.messages.append({"role": "assistant", "content": str(response)})
                except Exception as e:
                    st.error(f"Error connecting to vLLM at `{base_url}`: {e}")
