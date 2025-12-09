import pprint, time
import streamlit as st
from openai import OpenAI

st.title("Inferencing on Google Axion:c4a-standard-16")

# Set OpenAI API key from Streamlit secrets
client = OpenAI(base_url="http://10.128.0.13:11434/v1", api_key='no-key')

st.markdown('<style>' + open('styles.css').read() + '</style>', unsafe_allow_html=True)

#Set a default model
if "openai_model" not in st.session_state:
    st.session_state["openai_model"] = "gemma3:4b-highthread"

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if prompt := st.chat_input("What is up?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)

    # Display assistant response in chat message container
    with st.chat_message("assistant"), st.status(
        "Generating...", expanded=True
    ) as status:
        def get_streamed_completion(completion_generator):
            start = time.time()
            tokcount = 0
            for chunk in completion_generator:
                tokcount += 1
                if len(chunk.choices):
                    yield chunk.choices[0].delta.content

            status.update(
                label="Done, averaged {:.2f} tokens/second".format(
                    tokcount / (time.time() - start)
                ),
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
                        stream_options={"include_usage": True}
                        )
                    )
                )[0]
        except Exception as e:
            response = st.error(f"Error: {e}")
            print(e)

    st.session_state.messages.append({"role": "assistant", "content": response})

