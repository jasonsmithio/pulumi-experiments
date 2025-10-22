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

# Artifact Registry Repo for Docker Images
llm_repo = gcp.artifactregistry.Repository("llm-repo",
    location=gcp_region,
    repository_id="stablediffusion",
    description="Repo for Stable Diffusion usage",
    format="DOCKER",
    docker_config={
        "immutable_tags": True,
    }
)

# Docker image URL
torchserve_image = str(gcp_region)+"-docker.pkg.dev/"+str(gcp_project)+"/stablediffusion/gpu-torchserve"

# Docker image URL
openwebui_image = str(gcp_region)+"-docker.pkg.dev/"+str(gcp_project)+"/openwebui/openwebui"

# Build and Deploy GPU TorchServe Docker
torchserve_build = docker_build.Image('gputorchserve',
    tags=[torchserve_image],                                  
    context=docker_build.BuildContextArgs(
        location="./sd-handler/",
    ),
    platforms=[
        docker_build.Platform.LINUX_AMD64,
        docker_build.Platform.LINUX_ARM64,
    ],
    push=True,
)

# Build and Deploy OpenWeb UI Docker
openwebui_build = docker_build.Image('openwebui',
    tags=[openwebui_image],                                  
    context=docker_build.BuildContextArgs(
        location="./",
    ),
    platforms=[
        docker_build.Platform.LINUX_AMD64,
        docker_build.Platform.LINUX_ARM64,
    ],
    push=True,
)

# Ollama Cloud Run instance cloudrunv2 api
sd_cr_service = cloudrun.Service("sd_cr_service",
    name="stable-diffusion-service",
    location=gcp_region,
    deletion_protection= False,
    ingress="INGRESS_TRAFFIC_ALL",
    launch_stage="BETA",
    template={
        "containers":[{
            "image": torchserve_image,
            "resources": {
                "cpuIdle": False,
                "limits":{
                    "cpu": "8",
                    "memory": "32Gi",
                    "nvidia.com/gpu": "1",
                },
                "startup_cpu_boost": True,
            },
            "ports": {
                "container_port": 8080,
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
        "node_selector": {
            "accelerator": "nvidia-l4", 
        },
        "scaling": {      
            "max_instance_count":4,
            "min_instance_count":1,
        },
    },
    opts=pulumi.ResourceOptions(depends_on=[torchserve_build]),
)

torchserve_binding = cloudrun.ServiceIamBinding("torchserve-binding",
    project=gcp_project,
    location=gcp_region,
    name=sd_cr_service,
    role="roles/run.invoker",
    members=["allUsers"],
    opts=pulumi.ResourceOptions(depends_on=[sd_cr_service]),
)

torchserve_url = sd_cr_service.uri

# Open WebUI Cloud Run instance
openwebui_cr_service = cloudrun.Service("openwebui-service",
    name="openwebui-service",
    location=gcp_region,
    deletion_protection= False,
    ingress="INGRESS_TRAFFIC_ALL",
    launch_stage="BETA",
    template={
        "containers":[{
            "image": "us-central1-docker.pkg.dev/"+str(gcp_project)+"/openwebui/openwebui",
            "envs": [{
                "name":"OLLAMA_BASE_URL",
                "value":torchserve_url,
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
    opts=pulumi.ResourceOptions(depends_on=[torchserve_binding, openwebui_build]),
)

openwebui_binding = cloudrun.ServiceIamBinding("openwebui-binding",
    project=gcp_project,
    location=gcp_region,
    name=openwebui_cr_service,
    role="roles/run.invoker",
    members=["allUsers"],
    opts=pulumi.ResourceOptions(depends_on=[openwebui_cr_service]),
)


pulumi.export("torchserve_url", sd_cr_service.uri)
pulumi.export("open_webui_url", openwebui_cr_service.uri)