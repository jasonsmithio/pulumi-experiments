# axion-inferencing
Demo for inferencing on Axion

Set up steps:
- Start a c4a-standard-16 VM instance and ssh in
- To install ollama: curl -fsSL https://ollama.com/install.sh | sh
- export OLLAMA_HOST=$(hostname -I)
- To pull down the gemma3 model: ollama run gemma3:4b
- Then ctrl-C to stop
- To change the number of concurrent threads the model runs with:
    + ollama show --modelfile gemma3:4b > modelfile.txt
    + edit modelfile.txt and add the line 'PARAMETER num_thread 14'
    + ollama create -f ./modelfile.txt gemma3:4b-highthread
- Now run the new model: ollama run gemma3:4b-highthread

Now alter the app.py and deploy.sh scripts to point at the internal IP address of your ollama OpenAPI server
