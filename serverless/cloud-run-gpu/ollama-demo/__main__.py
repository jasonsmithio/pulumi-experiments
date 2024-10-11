import pulumi
from pulumi import Output, Config
import pulumi_gcp as gcp
import pulumi_docker as docker
import pulumi_docker_build as docker_build
from pulumi_gcp import cloudrunv2 as cloudrun


# Get some provider-namespaced configuration values
gconfig = pulumi.Config("gce")
gcp_project = gconfig.get("gcp:project")
# Get some provider-namespaced configuration values
config = pulumi.Config()
gcp_project = "cloudmium-1"
gcp_region = config.get("region", "us-central1")
gcp_zone = config.get("zone", "us-central1-a")
gke_network = config.get("gkeNetwork", "default")
gke_cluster_name = config.get("clusterName", "mixtral-cluster")
gke_master_version =config.get("master_version", 1.29)
gke_master_node_count = config.get_int("nodesPerZone", 1)

#setting unique values for the nodepool
gke_nodepool_name = config.get("nodepoolName", "mixtral-nodepool")
gke_nodepool_node_count = config.get_int("nodesPerZone", 2)
gke_ml_machine_type = config.get("mlMachines", "g2-standard-24")

# LLM Bucket

llm_bucket = gcp.storage.Bucket("llm-bucket",
    name=str(gcp_project)+"-llm-bucket",
    location=gcp_region,
    force_destroy=True,
    uniform_bucket_level_access=True,
    )

# Artifact Registry Repo for Docker Images
llm_repo = gcp.artifactregistry.Repository("llm-repo",
    location=gcp_region,
    repository_id="openwebui",
    description="Repo for Open WebUI usage",
    format="DOCKER",
    docker_config={
        "immutable_tags": True,
    }
)

# Open WebUI Container
#remote_image = docker.RemoteImage("openwebui-remote",
#    name="ghcr.io/open-webui/open-webui:main"  # Change this to the desired image
#)

# Tag the remote image
#tagged_image = docker.Tag("openwebui-tag",
#    source_image=remote_image.repo_digest,
#    target_image=str(gcp_region)+"-docker.pkg.dev/"+str(gcp_project)+"/openwebui/openwebui"  # Change this to the desired new tag and repository
#)

openwebui_image = str(gcp_region)+"-docker.pkg.dev/"+str(gcp_project)+"/openwebui/openwebui"

docker_image = docker_build.Image('openwebui',
    tags=[openwebui_image],                                  
    context=docker_build.BuildContextArgs(
        location="./",
    ),
    push=True,
)


# Export the tag URL
#pulumi.export("tagged_image_url", tagged_image.target_image)

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
    opts=pulumi.ResourceOptions(depends_on=[ollama_binding, docker_image]),
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
pulumi.export("open_webui_url", openwebui_cr_service.uri)