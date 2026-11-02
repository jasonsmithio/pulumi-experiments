import os
import pathlib
import time
import streamlit as st
from openai import OpenAI

st.set_page_config(
    page_title="Gemma 4 on Google Axion (GKE C4A)",
    page_icon="⚡",
    layout="centered",
)

css_path = pathlib.Path(__file__).parent / "styles.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

DEFAULT_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama-service:11434/v1")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:4b-highthread")
MACHINE_TYPE = os.environ.get("AXION_MACHINE_TYPE", "c4a-standard-16")

st.title(f"Inferencing on Google Axion: {MACHINE_TYPE}")
st.caption("Running Gemma 4 on GKE Arm Neoverse V2 (C4A) CPU nodes with Hyperdisk Balanced storage")

with st.sidebar:
    st.header("⚙️ GKE Axion Configuration")
    model_choice = st.selectbox(
        "Ollama Model",
        options=["gemma4:4b-highthread", "gemma4:4b"],
        index=0 if DEFAULT_MODEL == "gemma4:4b-highthread" else 1,
        help="Compare 14-thread tuned Gemma 4 (`num_thread 14`) vs. default thread allocation on `c4a-standard-16`.",
    )
    base_url = st.text_input(
        "Ollama OpenAI Endpoint",
        value=DEFAULT_BASE_URL,
        help="In-cluster Kubernetes Service URL (`http://ollama-service:11434/v1`) or external Gateway URL.",
    )
    if st.button("Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.session_state["openai_model"] = model_choice
client = OpenAI(base_url=base_url, api_key=os.environ.get("OPENAI_API_KEY", "no-key"))

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask Gemma 4 on GKE Axion..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"), st.status(
        f"Streaming from `{st.session_state['openai_model']}` on `{MACHINE_TYPE}`...",
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
                label=f"Done — averaged {tokcount / elapsed:.2f} tokens/second ({st.session_state['openai_model']})",
                state="complete",
            )

        try:
            response = st.write_stream(
                get_streamed_completion(
                    client.chat.completions.create(
                        model=st.session_state["openai_model"],
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
            st.error(f"Error connecting to Ollama at `{base_url}`: {e}")
