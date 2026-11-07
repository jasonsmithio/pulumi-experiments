# Recaps

Session-by-session log of completed work, newest first.

## 2026-11-06

### Sync GitLab and GitHub remotes & resolve GH007 mirror failure

- Added `gitlab` remote (`git@gitlab.com:jasonsmithio/pulumi-experiments.git`) and rebased `main` (`9ace5ee`, `4d6b22f`) onto `gitlab/main` (`daed660`, `4996f7f`, `025309c`) to resolve divergent histories between GitLab and GitHub.
- Diagnosed the subsequent GitLab → GitHub push mirror failure via `glab api`: commit `185f1d8` (*"Switch gke-with-axion and Streamlit ADK container to uv"*) was authored/committed with private email `jaysmith@google.com`, triggering GitHub's `GH007` email privacy rejection.
- Rewrote the `uv` migration commit (`6e70e72`) with `7904755+jasonsmithio@users.noreply.github.com`, synced `gitlab/main` and `origin/main`, and rebased local `rena-round1` (`cloud-run-gpu/rena`) onto the updated `main`.

## 2026-06-23

### Fix Dependabot langchain alerts in ollama-rag demos

- Resolved all 6 open Dependabot alerts (langchain `<= 1.3.8` path-traversal / sandbox-escape, medium) by upgrading langchain to `>=1.3.9,<2.0.0` across both copies of the `ollama-rag` demo (`serverless/cloud-run-gpu/ollama-rag` and `serverless/cloud-run/cr-gpu/ollama-rag`, which are byte-identical).
- The fix required a langchain 0.3 → 1.x major bump (no 0.3.x patch exists). Companion pins bumped for core 1.x compatibility: `langchain-community>=0.4.0`, `langchain-google-vertexai>=3.0.0`, `langchain-google-community>=5.0.0`, `langchain-google-alloydb-pg>=0.15.0`, `langserve>=0.3.3` (0.3.3 relaxed its core cap to `<2`).
- Code ports: streamlit `app.py` moved `langchain.llms.Ollama` → `langchain_ollama.OllamaLLM` (added `langchain-ollama` dep, dropped unused `langchain-community`/`langchain-google-community` + two unused imports); indexer `indexer.py` dropped the unused `langchain.llms.Ollama` import and **kept** `langchain_community.vectorstores.pgvector.PGVector` (still ships in community 0.4.2) to preserve the pg8000 AlloyDB connector — `langchain-postgres` was rejected because it hard-requires psycopg3/asyncpg.
- Verified all three requirement sets resolve in a clean venv (langchain 1.3.11 / core 1.4.8 / community 0.4.2) and all four Python files compile.
- Open follow-ups: the two ollama-rag trees are exact duplicates (worth de-duping); root `requirements.txt` still carries langchain/streamlit/fastapi/langserve that `__main__.py` (pure Pulumi) never imports; `VertexAIEmbeddings(model_name="textembedding-gecko@003")` uses a Google-retired embedding model — runtime-untested here.
