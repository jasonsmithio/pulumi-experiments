# Run Cloud Run on Wordpress (WIP)

This code will show you how to install a fresh [WordPress](https://wordpress.org "WordPress") installation on [Cloud Run](https://cloud.run "Cloud Run"). The WordPress application will live on Cloud Run while the data will be stored in a MySQL 8.0 database on [Google Cloud SQL](https://cloud.google.com/sql "Cloud SQL"). We will also store assets such as uploaded images in a [Cloud Storage](https://cloud.google.com/storage "Cloud Storage") bucket.

This will all be deployed utilizing [Pulumi](https://pulumi.com) as an IaC and [Python](https://python.org) language. 

## Preparing the Deploy

First we will need to set some environment variables

```bash
export PROJECT_ID=<your-project-id>
export REGION="us-central1" #or your preferred region
export ZONE=${REGION}-a 
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export GCE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
```

### Configure that Google Cloud Platform (GCP) environment

Now that the variables are set, let's make sure that your GCP environment is setup and that your terminal is properly setup and authenticated to interface with GCP.

```bash
gcloud auth login 
gcloud config set project $PROJECT_ID 
gcloud config set compute/region $REGION
gcloud config set compute/zone $ZONE
gcloud auth application-default login
```

### Enable some Google Cloud APIs

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

### Enabling Logs

And finally, we'll do set a few more environment variables and perform some IAM binding. In short, this will give our Cloud Run services the ability to write logs.


```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
--member=serviceAccount:${GCE_SA} --role=roles/storage.admin
gcloud projects add-iam-policy-binding $PROJECT_ID \
--member=serviceAccount:${GCE_SA} --role=roles/monitoring.metricWriter
gcloud projects add-iam-policy-binding $PROJECT_ID \
--member=serviceAccount:${GCE_SA} --role=roles/stackdriver.resourceMetadata.writer
```

Now that we have the basics setup, let's pull down the code

## Getting Started with Pulumi 


```bash
git clone https://github.com/jasonsmithio/pulumi-experiments
cd pulumi-experiments/serverless/cloud-run/cr-wordpress/
```

Now let's create a Pulumi stack. You can name the stack whatever you want but `wordpress` is a good stack name.

```bash
pulumi stack init
```

### Setting some Pulumi Variables

```bash
pulumi config set gcp:project $PROJECT_ID
pulumi config set gcp:region $REGION
pulumi config set db-name wordpress-db # You can change this if you really want to
```

Notice that some of these variables were set earlier


## Pulumi and Python

You will see that I have a `__main__.py` file in the main directory. This program will tell Pulumi todo a few things. 

- Import the relevant Python libraries ( lines 1-6 )
- Setup all the environment variables for later use ( lines 8-11 )
- It will create a bucket in Google Cloud Storage to store our WordPress assets. ( lines 13-19 )
- 

This is all Python code. We aren't using a bespoke Domain Specific Language (DSL) such as Hashicorp's HCL. Since this is just Python, it is really easy to add to your workflow. 

## Let Pulumi build you resources!

We will execute now let Pulumi take our Python program and deploy.

```bash
pulumi up
```
It will run a test first to make sure that everything looks good. After that test runs, it will ask you if you want to execute so choose `yes` and deploy. This can take a few minutes to launch but I want you to take notice of how long it takes the `ollama_cr_service` to run.

![pulumi-services](./images/pulumi-wordpress-1.png)


![pulumi-services](./images/wordpress-login-1.png)


## Clean Up

Best practices are to always clean up after your experiments. Simply enter the below command.

```bash
pulumi destroy
```

choose `yes` to destroy and in about 5 - 10 minutes, everything will be removed. 