import os
from typing import List
from fastapi import FastAPI
from langchain.llms import Ollama
from langchain.output_parsers import CommaSeparatedListOutputParser
from langchain.prompts import PromptTemplate
import streamlit

ollama_url = os.environ["OLLAMA_BASE_URL"]

llm = Ollama(model="gemma2:2b", base_url=ollama_url, verbose=True)

def sendPrompt(prompt):
    global llm
    response = llm.invoke(prompt)
    return response

streamlit.title("Chat with Ollama")
if "messages" not in streamlit.session_state.keys(): 
    streamlit.session_state.messages = [
        {"role": "assistant", "content": "Ask me a question !"}
    ]

if prompt := streamlit.chat_input("Your question"): 
    streamlit.session_state.messages.append({"role": "user", "content": prompt})

for message in streamlit.session_state.messages: 
    with streamlit.chat_message(message["role"]):
        streamlit.write(message["content"])
        
if streamlit.session_state.messages[-1]["role"] != "assistant":
    with streamlit.chat_message("assistant"):
        with streamlit.spinner("Thinking..."):
            response = sendPrompt(prompt)
            print(response)
            streamlit.write(response)
            message = {"role": "assistant", "content": response}
            streamlit.session_state.messages.append(message) 