import pulumi
from pulumi import Output, Config
import pulumi_gcp as gcp
import pulumi_docker as docker
import pulumi_docker_build as docker_build
from pulumi_gcp import cloudrunv2 as cloudrun

# Get some provider-namespaced configuration values such as project
gconfig = pulumi.Config("gcp")
gcp_project = gconfig.require("project")
gcp_region = gconfig.get("region", "us-central1")
gcp_zone = gconfig.get("zone", "us-central1-a")

# LLM Bucket
llm_bucket = gcp.storage.Bucket("llm-bucket",
    name=str(gcp_project)+"-llm-bucket",
    location=gcp_region,
    force_destroy=True,
    uniform_bucket_level_access=True,
    )

# Artifact Registry Repo for AI Docker Images
ai_gar = gcp.artifactregistry.Repository("agent-repo",
    location=gcp_region,
    repository_id="agents",
    description="Repo for AI Agents running on Cloud Run",
    format="DOCKER",
    docker_config={
        "immutable_tags": True,
    }
)

# Ollama Docker Image URL
ollama_repo = str(gcp_region)+"-docker.pkg.dev/"+str(gcp_project)+"/agents/ollama:latest"

# Build and Deploy Ollama Docker Image
ollama_image = docker_build.Image('ollama-image',
    tags=[ollama_repo],                                  
    context=docker_build.BuildContextArgs(
        location="./ollama/",
    ),
    platforms=[
        docker_build.Platform.LINUX_AMD64,
        docker_build.Platform.LINUX_ARM64,
    ],
    push=True,
)

# Agent Docker image URL
agent_repo = str(gcp_region)+"-docker.pkg.dev/"+str(gcp_project)+"/agents/agent-image"

# Build and Deploy Docker
agent_image = docker_build.Image('agent-image',
    tags=[agent_repo],                                  
    context=docker_build.BuildContextArgs(
        location="./adk-agent/prod/",
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
            "image": ollama_image,
            "envs": [{
                "name":"OLLAMA_NUM_PARALLEL",
                "value":4,
            }],
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
        "gpu_zonal_redundancy_disabled": True,
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

# Open WebUI Cloud Run instance
agent_cr_service = cloudrun.Service("agent-service",
    name="adk-agent-service",
    location=gcp_region,
    deletion_protection= False,
    ingress="INGRESS_TRAFFIC_ALL",
    launch_stage="BETA",
    template={
        "containers":[{
            "image": agent_image,
            "envs": [{
                "name":"GOOGLE_CLOUD_PROJECT",
                "value":gcp_project,
            }
            ,{
                "name":"GOOGLE_CLOUD_LOCATION",
                "value": gcp_region,  
            },{
                "name":"GEMMA_MODEL_NAME",
                "value":"gemma3:270m",
            },{
                "name":"OLLAMA_API_BASE",
                "value":ollama_url,
            }],
            "resources": {
                "cpuIdle": False,
                "limits":{
                    "cpu": "2",
                    "memory": "4Gi",
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
            "max_instance_count":2,
            "min_instance_count":1,
        },
    },
    traffics=[{
        "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST",
        "percent": 100,
    }],
    opts=pulumi.ResourceOptions(depends_on=[ollama_binding, ollama_image]),
)

agent_binding = cloudrun.ServiceIamBinding("agent-binding",
    project=gcp_project,
    location=gcp_region,
    name=agent_cr_service,
    role="roles/run.invoker",
    members=["allUsers"],
    opts=pulumi.ResourceOptions(depends_on=[agent_cr_service]),
)


pulumi.export("ollama_url", ollama_cr_service.uri)
pulumi.export("open_webui_url", agent_cr_service.uri)