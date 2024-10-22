# Cloud Run with GPUs attached Pulumi demo

**>>NOTE This product isn't GA yet but you can request being added to the allowlist by filling out [this form](g.co/cloudrun/GPU).<<**

On August 21, 2024 Google Cloud [announced](https://cloud.google.com/blog/products/application-development/run-your-ai-inference-applications-on-cloud-run-with-nvidia-gpus) that [Cloud Run](https://cloud.run/) now supports GPUs. This means that GPUs can run in a serverless environment. It follows that same pay-per-use model as Cloud Run and other serverless products in the market. It can also scale-to-zero and autoscaling! 

One of the coolest things about this is that we have significantly reduced the cold start process of GPUs so you can launch an LLM service with a GPU attached and be ready to inference with it in under a minute. Normally, it takes at least a minute to just install GPU drivers on VMs. This offering is game changing in the world of Generative AI.

In this tutorial, I will show you how to deploy an LLM on Cloud Run with GPUs attached and it will take less than a minute. We will be leveraging the [Gemma 2](https://developers.googleblog.com/en/gemma-explained-new-in-gemma-2/) 2B LLM and will be serving it with [Ollama](https://ollama.com/).  

We will also deploy a Cloud Run service with [Open WebUI](https://openwebui.com/) to help us interface. 


## What is Gemma 2?

Gemma is a family of open-use, lightweight LLMs provided by Google that anyone can use to greate Generative AI applications. I don't like to call it "Open Source" because it technically isn't. Google refers to it as an ["open model"](https://opensource.googleblog.com/2024/02/building-open-models-responsibly-gemini-era.html). The distinction is that with true open source licenses, the user can theoretically do whatever they want with the software. 

Generative AI and LLMs are a bit different. They are incredibly useful tools but they can also be misused very easily for things that violate [Google's Principles around AI Responsibility](https://ai.google/responsibility/principles/). So people are free to use Gemma but there are restrictions to prevent misuse.

That aside, it is a very powerful LLM and it's free to use pretty much wherever you please. You could run it on your laptop or in the cloud. 

## What is Ollama?

Ollama is an open source project that makes it easier to use and consume LLMs. One way to think about it is that if the LLM is an application, Ollama is the operating system or platform that the LLM runs on. To use an LLM you have to interface with it in some way. While you could create custom software to accomplish this, there are a number of powerful tools that simpilifies the experience in a user-friendly way. 

Ollama is the one that I have chosen for this demo. Ollama just works. It is simple to setup and use for inferencing and integrates great with Python if you are building binaries to inference with the LLM. It's also lightweight enough for this demo. 

Ollama supports [many different LLMs](https://ollama.com/library) so you could do this demo with [Mistral NeMo](https://mistral.ai/news/mistral-nemo/) or [Llama 3.2](https://ai.meta.com/blog/llama-3-2-connect-2024-vision-edge-mobile-devices/) or any number of other LLMs supported by Ollama. I just chose Ollama and Gemma. 

## What is Open WebUI?

Open WebUI is an open source UI for LLMs. Rather than trying to develop your own UI, you can leverage this to help you work with Ollama. You can also developer your own using the [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md) but for our purposes, this is simpler.

So let's get started. 

## Some Pre-requesites 

### Before we get started... 
Make sure you have access to a Google Cloud project that supports NVIDIA L4s in your desired region per your quotas. This tutorial uses `us-central1` for the moment as Cloud Run GPUs isn't GA yet and is in limited regions. 

We will also be using [Pulumi](https://www.pulumi.com/) for this demo. You can create a free account at [https://app.pulumi.com/signup](https://app.pulumi.com/signup) if you don't already have one. They also provide some useful "getting started" docs [here](https://www.pulumi.com/docs/iac/get-started/).

We will also be using Pulumi to create a Docker container using their new [Docker Build Provider](https://www.pulumi.com/blog/docker-build/). This will work best if you have Docker installed. If you don't, you can do so by following [these instructions](https://docs.docker.com/engine/install/).

Finally, make sure that your Google Cloud user has the `iam.allowedPolicyMemberDomains` permissions. 

### Some Environment Variables

Before we get started, we will set a few basic environment variables in our terminal. This will make things easier for us as we move forward. Copy and paste the below snippet into your terminal. Be sure to set your `PROJECT_ID` and `NETWORK`. You may be able to set the network to *default* as there is usually a default network in a brand new environment.  

```bash
export PROJECT_ID=<your-project-id>
export REGION="us-central1"
export ZONE=${REGION}-a 
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export GCE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
```

### Configuring the Google Cloud Platform (GCP) environment

Now that the variables are set, let's make sure that your GCP environment is setup and that your terminal is properly setup and authenticated to interface with GCP. The final line is going to be useful later when we build our Docker container as it will setup `gcloud` as a [Docker Credentials Helper](https://github.com/docker/docker-credential-helpers).


```bash
gcloud auth login 
gcloud config set project $PROJECT_ID 
gcloud config set compute/region $REGION
gcloud config set compute/zone $ZONE
gcloud auth application-default login
gcloud auth configure-docker ${REGION}-docker.pkg.dev
```

Now that we are authenticated, let's enable some APIs. Every resource in Google Cloud has an API that needs to be enabled. By default, new projects have all APIs turned off so if you are just getting started, it's important to turn them on. You only need to do this once. 

```bash
gcloud services enable \
        cloudresourcemanager.googleapis.com \
        compute.googleapis.com \
        container.googleapis.com \
        cloudbuild.googleapis.com \
        containerregistry.googleapis.com \
        storage.googleapis.com \
        run.googleapis.com
```

And finally, we'll do set a few more environment variables and perform some IAM binding. In short, this will give our Cloud Run services the ability to write logs.

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
--member=serviceAccount:${GCE_SA} --role=roles/storage.admin
gcloud projects add-iam-policy-binding $PROJECT_ID \
--member=serviceAccount:${GCE_SA} --role=roles/monitoring.metricWriter
gcloud projects add-iam-policy-binding $PROJECT_ID \
--member=serviceAccount:${GCE_SA} --role=roles/stackdriver.resourceMetadata.writer
```
This CAN be configured in Pulumi but for the purposes of this demo, we will set it in terminal. In a future demo, I may show you how to use their new [ESC](https://www.pulumi.com/product/secrets-management/) feature.


### Clone Demo Code from GitHub

In whatever directory you want to execute this code, run the below command in the terminal. It will pull down this GitHub repo and place you in the folder

```bash
git clone https://github.com/jasonsmithio/pulumi-experiments
cd pulumi-experiments/serverless/cloud-run-gpu/ollama-demo
```

### Staging Pulumi Environment

The first thing we need to do is setup a [Pulumi Stack](https://www.pulumi.com/docs/iac/concepts/stacks/).

```bash
pulumi stack init
```

It will ask you to name your stack so name it whatever you choose (e.g. `ollama-demo`).

### Settings some variables

In our Python demo, we will be standing up a GKE Cluster. Pulumi allows us to [configure](https://www.pulumi.com/docs/concepts/config/) environment variables in a `Pulumi.<env>.yaml` file. While you can manually build the file, you can also just execute the commands below.

```bash
pulumi config set gcp:project $PROJECT_ID
pulumi config set gcp:region $REGION
pulumi config set gcp:zone $ZONE
```

Notice how we are using some of the variables we set earlier.


## Pulumi and Python

You will see that I have a `__main__.py` file in the main directory. This program will tell Pulumi todo a few things. 

- Import the relevant Python libraries ( lines 1-6 )
- Setup all the environment variables for later use ( lines 9-13 )
- It will create a bucket in Google Cloud Storage to store our LLMs ( lines 15-21 )
- Create a repo in [Google Artifact Registry](https://cloud.google.com/artifact-registry/docs) for our Docker container. ( Lines 23-32 )
- Build an Open WebUI container and push it to Artifact Registry ( lines 34-44 )
- Create a Cloud Run service running Ollama with 1 [NVIDIA L4](https://cloud.google.com/blog/products/compute/introducing-g2-vms-with-nvidia-l4-gpus) GPU attached and change the [IAM](https://cloud.google.com/security/products/iam) settings to make the URL publicly accessible.( lines 46-108 )
- Create a Cloud Run service running Open WebUI  change the [IAM](https://cloud.google.com/security/products/iam) settings to make the URL publicly accessible.( lines 110-165 )
- Outputs for the URLs of both Cloud Run servers ( line 168 & 169 )

This is all Python code. We aren't using a bespoke Domain Specific Language (DSL) such as Hashicorp's HCL. Since this is just Python, it is really easy to add to your workflow. 

## Let Pulumi build you resources!

We will execute now let Pulumi take our Python program and deploy.

```bash
pulumi up
```

It will run a test first to make sure that everything looks good. After that test runs, it will ask you if you want to execute so choose `yes` and deploy. This can take a few minutes to launch but I want you to take notice of how long it takes the `ollama_cr_service` to run.

![pulumi-services](./images/pulumi-services.png)

**52 Seconds!** You have an LLM deployed with a GPU attached and ready to go in under a minute! This is mind blowing! Anyone who has provisioned machines with GPUs will tell you that this is amazing. 

When you are ready you should see something like this 

![pulumi-complete](./images/pulumi-complete.png)

If you see this, we are ready to test. But before we move to the next step, you should see a section called "Outputs" and under that `ollama_url` followed by a URL. Copy that URL and save it into a variable

```bash
URL=<your ollama_url>
```

This will come in handy later. So let's move forward. 

### Testing

You have a few ways to test this. 

#### Ollama CLI

Ollama has a nice CLI tool. You can install it by checking the instructions [here](https://github.com/ollama/ollama) that's relevant to your OS.

If you are using a *nix OS, you can now run the following command to download Gemma2:2b

```bash
OLLAMA_HOST=$URL ollama run gemma2:2b
```

The initial run will take a few minutes to complete. This is became Ollama is downloading the LLM and will be storing it in a mounted [Google Cloud Storage Bucket](https://cloud.google.com/storage). This way, if you want to use the same LLM in the future, it will not have to download the LLM and just inference. 

When done, you should see something like this:

```bash
>>> Send a message (/? for help)
```

If you see that, you are ready to inference. Ask the LLM a question such as "which Final Fantasy is the best" and see what happens. 


#### Open Web UI

Back in your terminal, you should see an output for `open_webui_url`. Copy that URL and put it in your browser. This will launch Open WebUI for you. 

In the upper right hand corner, you should see "Select A Model". Choose `gemma2:2b1` and then type a question in the "How Can I help you today?" bar. Ask your question and see what happens. 

I would recommend doing this after the CLI as it will download `gemma2:2b` for you and you won't have to do it in the UI. 

## Clean Up

Best practices are to always clean up after your experiments. Simply enter the below command.

```bash
pulumi destroy
```

choose `yes` to destroy and in about 5 minutes, everything will be removed. 

