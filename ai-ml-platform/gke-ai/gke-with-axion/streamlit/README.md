# axion-inferencing (Gemma 4 on GKE Axion)
Streamlit OpenAI-compatible client for benchmarking **Gemma 4** (`gemma4:4b` vs. `gemma4:4b-highthread`) on Google Cloud Axion (`c4a-standard-16`) processors.

## Environment Variables
- `OLLAMA_BASE_URL`: Defaults to `http://ollama-service:11434/v1` (in-cluster GKE Service).
- `OLLAMA_MODEL`: Defaults to `gemma4:4b-highthread` (`PARAMETER num_thread 14`).
- `AXION_MACHINE_TYPE`: Defaults to `c4a-standard-16`.

## Manual Ollama Setup Steps (if running on a standalone C4A VM or via `kubectl exec`)
1. Connect to your `c4a-standard-16` node or Ollama pod (`kubectl exec -it statefulset/ollama -- bash`)
2. Pull the base **Gemma 4 4B** model:
   ```bash
   ollama pull gemma4:4b
   ```
3. Configure 14 CPU threads to saturate `c4a-standard-16` (reserving 2 vCPUs for kubelet/OS):
   ```bash
   ollama show --modelfile gemma4:4b > modelfile.txt
   # Add 'PARAMETER num_thread 14' to modelfile.txt
   ollama create -f ./modelfile.txt gemma4:4b-highthread
   ```
4. Test the tuned model:
   ```bash
   ollama run gemma4:4b-highthread
   ```
