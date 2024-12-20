import os
import pulumi
from pulumi import Output, Config
import pulumi_gcp as gcp
import pulumi_docker as docker
import pulumi_docker_build as docker_build
from pulumi_gcp import cloudrunv2 as cloudrun
import pulumi_random as random


# Get some provider-namespaced configuration values such as project

gconfig = pulumi.Config("gcp")
gcp_project = gconfig.require("project")
gcp_region = gconfig.get("region", "us-central1")
gcp_zone = gconfig.get("zone", "us-central1-a")
#gcp_network = gconfig.get("network", "default")

pconfig = pulumi.Config()
gcp_network = pconfig.get("network", "default")

# Create AlloyDB Password for Later
rag_alloydb_password = random.RandomPassword("password",
    length=24,
    special=True,
    override_special="!#$%&*()-_=+[]{}<>:?")

# PDF Bucket
pdf_bucket = gcp.storage.Bucket("pdf-bucket",
    name=str(gcp_project)+"-pdf-bucket",
    location=gcp_region,
    force_destroy=True,
    uniform_bucket_level_access=True,
    )

# Get PDF Names
pdf_objects= []

def list_pdfs(directory):
    pdf_files = []
    for filename in os.listdir(directory):
        if filename.endswith(".pdf"):
            pdf_files.append(filename)
    return pdf_files

pdf_path = "./pdfs/"
pdfs = list_pdfs(pdf_path)

# Upload PDFs to PDF Bucket
for file in pdfs:
    bucket_object = gcp.storage.BucketObject(
        file.replace(".pdf", ""),  # Using file name as resource name
        bucket=pdf_bucket.name,
        source=pulumi.FileAsset(file)
    )
    pdf_objects.append(bucket_object)


# LLM Bucket
llm_bucket = gcp.storage.Bucket("llm-bucket",
    name=str(gcp_project)+"-llm-bucket",
    location=gcp_region,
    force_destroy=True,
    uniform_bucket_level_access=True,
    )

# AlloyDB Setup for RAG

# Create AlloyDB Cluster

rag_alloydb_cluster = gcp.alloydb.Cluster("rag_alloydb_cluster",
    cluster_id="alloydb-cluster",
    location="us-central1",
    network_config={
        "network": gcp_network,
    })

rag_alloydb_instance = gcp.alloydb.Instance("default",
    cluster=rag_alloydb_cluster.name,
    instance_id="alloydb-instance",
    instance_type="PRIMARY",
    machine_config={
        "cpu_count": 2,
    },
    opts = pulumi.ResourceOptions(depends_on=[rag_alloydb_cluster]))

rag_alloydb_user = gcp.alloydb.User("rag_alloydb_user",
    cluster=rag_alloydb_cluster.name,
    user_id="user1",
    user_type="ALLOYDB_BUILT_IN",
    password=rag_alloydb_password.result,
    database_roles=["alloydbsuperuser"],
    opts = pulumi.ResourceOptions(depends_on=[rag_alloydb_instance]))

# Artifact Registry Repo for Docker Images
llm_repo = gcp.artifactregistry.Repository("llm-repo",
    location=gcp_region,
    repository_id="ollama-demo",
    description="Repo for Open WebUI usage",
    format="DOCKER",
    docker_config={
        "immutable_tags": True,
    }
)

# Docker image URLs
streamlit_image = str(gcp_region)+"-docker.pkg.dev/"+str(gcp_project)+"/ollama-demo/streamlit"
openwebui_image = str(gcp_region)+"-docker.pkg.dev/"+str(gcp_project)+"/ollama-demo/openwebui"
indexer_image = str(gcp_region)+"-docker.pkg.dev/"+str(gcp_project)+"/ollama-demo/indexer"

# Build and Deploy Docker Images
streamlit_build = docker_build.Image('streamlit',
    tags=[streamlit_image],                                  
    context=docker_build.BuildContextArgs(
        location="apps/streamlit",
    ),
    platforms=[
        docker_build.Platform.LINUX_AMD64,
        docker_build.Platform.LINUX_ARM64,
    ],
    push=True,
)

indexer_build = docker_build.Image('indexer',
    tags=[indexer_image],                                  
    context=docker_build.BuildContextArgs(
        location="./apps/indexer/",
    ),
    platforms=[
        docker_build.Platform.LINUX_AMD64,
        docker_build.Platform.LINUX_ARM64,
    ],
    push=True,
)

openwebui_build = docker_build.Image('openwebui',
    tags=[openwebui_image],                                  
    context=docker_build.BuildContextArgs(
        location="apps/openwebui",
    ),
    platforms=[
        docker_build.Platform.LINUX_AMD64,
        docker_build.Platform.LINUX_ARM64,
    ],
    push=True,
)

# Ollama Cloud Run instance cloudrunv2 api
ollama_cr_service = cloudrun.Service("ollama_cr_service",
    name="ollama-service",
    location=gcp_region,
    deletion_protection= False,
    ingress="INGRESS_TRAFFIC_ALL",
    launch_stage="BETA",
    template={
        "containers":[{
            "image": "ollama/ollama",
            "resources": {
                "cpuIdle": False,
                "limits":{
                    "cpu": "8",
                    "memory": "16Gi",
                    "nvidia.com/gpu": "1",
                },
                "startup_cpu_boost": True,
            },
            "ports": {
                "container_port": 11434,
            },
            "volume_mounts": [{
                "name": "ollama-bucket",
                "mount_path": "/root/.ollama/",
            }],
            "startup_probe": {
                "initial_delay_seconds": 0,
                "timeout_seconds": 1,
                "period_seconds": 1,
                "failure_threshold": 1800,
                "tcp_socket": {
                    "port": 11434,
                },
            },
        }],
        "node_selector": {
            "accelerator": "nvidia-l4", 
        },
        "scaling": {      
            "max_instance_count":4,
            "min_instance_count":1,
        },
        "volumes":[{
            "name": "ollama-bucket",
            "gcs": {
                "bucket": llm_bucket.name,
                "read_only": False,
            },
        }],
    },
)

ollama_binding = cloudrun.ServiceIamBinding("ollama-binding",
    project=gcp_project,
    location=gcp_region,
    name=ollama_cr_service,
    role="roles/run.invoker",
    members=["allUsers"],
    opts=pulumi.ResourceOptions(depends_on=[ollama_cr_service]),
)

ollama_url = ollama_cr_service.uri

# Streamlit Cloud Run instance
streamlit_cr_service = cloudrun.Service("streamlit-service",
    name="streamlit-service",
    location=gcp_region,
    deletion_protection= False,
    ingress="INGRESS_TRAFFIC_ALL",
    launch_stage="BETA",
    template={
        "containers":[{
            "image": streamlit_image,
            "envs": [{
                "name":"OLLAMA_BASE_URL",
                "value":ollama_url,
            }],
            "resources": {
                "cpuIdle": False,
                "limits":{
                    "cpu": "8",
                    "memory": "16Gi",
                },
                "startup_cpu_boost": True,
            },
            "startup_probe": {
                "initial_delay_seconds": 0,
                "timeout_seconds": 1,
                "period_seconds": 1,
                "failure_threshold": 1800,
                "tcp_socket": {
                    "port": 8080,
                },
            },
        }],
        "scaling": {      
            "max_instance_count":4,
            "min_instance_count":1,
        },
    },
    traffics=[{
        "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST",
        "percent": 100,
    }],
    opts=pulumi.ResourceOptions(depends_on=[ollama_binding, streamlit_build]),
)

streamlit_binding = cloudrun.ServiceIamBinding("streanlit-binding",
    project=gcp_project,
    location=gcp_region,
    name=streamlit_cr_service,
    role="roles/run.invoker",
    members=["allUsers"],
    opts=pulumi.ResourceOptions(depends_on=[streamlit_cr_service]),
)

# Indexer Cloud Run instance
indexer_cr_job = cloudrun.Job("indexer-service",
    name="indexer-service",
    location=gcp_region,
    deletion_protection= False,
    launch_stage="BETA",
    template={
        "containers":[{
            "image": indexer_image,
            "envs": [{
                "name":"RAG_DB_INSTANCE_NAME",
                "value":"rag_alloydb_instance",
            },{
                "name":"RAG_DB_USER",
                "value":"rag_alloydb_user",  
            },{
                "name":"RAG_DB_PASS",
                "value": rag_alloydb_password.result,
            },{
                "name":"RAG_DB_NAME",
                "value":"RAG_DB",
            }],
            "resources": {
                "cpuIdle": False,
                "limits":{
                    "cpu": "2",
                    "memory": "4Gi",
                },
                "startup_cpu_boost": True,
            },
            "volume_mounts": [{
                "name": "pdf-bucket",
                "mount_path": "/root/.training/",
            }],
            "startup_probe": {
                "initial_delay_seconds": 0,
                "timeout_seconds": 1,
                "period_seconds": 1,
                "failure_threshold": 1800,
                "tcp_socket": {
                    "port": 8080,
                },
            },
        }],
        "scaling": {      
            "max_instance_count":3,
            "min_instance_count":0,
        },
        "volumes":[{
            "name": "pdf-bucket",
            "gcs": {
                "bucket": pdf_bucket.name,
                "read_only": False,
            },
        }],
    },
    opts=pulumi.ResourceOptions(depends_on=[ollama_binding, streamlit_build]),
)

indexer_binding = cloudrun.ServiceIamBinding("indexer-binding",
    project=gcp_project,
    location=gcp_region,
    name=indexer_cr_job,
    role="roles/run.invoker",
    members=["allUsers"],
    opts=pulumi.ResourceOptions(depends_on=[indexer_cr_job]),
)


# Open WebUI Cloud Run instance
openwebui_cr_service = cloudrun.Service("openwebui-service",
    name="openwebui-service",
    location=gcp_region,
    deletion_protection= False,
    ingress="INGRESS_TRAFFIC_ALL",
    launch_stage="BETA",
    template={
        "containers":[{
            "image": openwebui_image,
            "envs": [{
                "name":"OLLAMA_BASE_URL",
                "value":ollama_url,
            }
            ,{
                "name":"WEBUI_AUTH",
                "value":'false',  
            }],
            "resources": {
                "cpuIdle": False,
                "limits":{
                    "cpu": "8",
                    "memory": "16Gi",
                },
                "startup_cpu_boost": True,
            },
            "startup_probe": {
                "initial_delay_seconds": 0,
                "timeout_seconds": 1,
                "period_seconds": 1,
                "failure_threshold": 1800,
                "tcp_socket": {
                    "port": 8080,
                },
            },
        }],
        "scaling": {      
            "max_instance_count":4,
            "min_instance_count":1,
        },
    },
    traffics=[{
        "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST",
        "percent": 100,
    }],
    opts=pulumi.ResourceOptions(depends_on=[ollama_binding, openwebui_build]),
)

openwebui_binding = cloudrun.ServiceIamBinding("openwebui-binding",
    project=gcp_project,
    location=gcp_region,
    name=openwebui_cr_service,
    role="roles/run.invoker",
    members=["allUsers"],
    opts=pulumi.ResourceOptions(depends_on=[openwebui_cr_service]),
)


pulumi.export("ollama_url", ollama_cr_service.uri)
pulumi.export("streamlit_url", streamlit_cr_service.uri)
pulumi.export("open_webui_url", openwebui_cr_service.uri)