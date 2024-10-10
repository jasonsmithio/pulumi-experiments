import pulumi
from pulumi import Output, Config
import pulumi_gcp as gcp
from pulumi_gcp import cloudrunv2 as cloudrun
from pulumi_gcp.cloudrun import (
    ServiceTemplateMetadataArgs,
    ServiceTemplateSpecContainerEnvArgs,
)


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

# Ollama Cloud Run instance cloudrunv2 api
ollama_cr_service = cloudrun.Service("ollama_cr_service",
    name="ollama-service",
    location=gcp_region,
    ingress="INGRESS_TRAFFIC_ALL",
    launch_stage="GA",
    template={
        "containers":[{
            "image": "ollama/ollama",
            "resources": {
                "cpuIdle": True,
                "limits":{
                    "cpu": "8",
                    "memory": "16Gi",
                    "nvidia_com_gpu": "1",
                },
                "startup_cpu_boost": True,
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
        #"execution_environment": "EXECUTION_ENVIRONMENT_GEN2",
    }
)



ollama_url = ollama_cr_service.uri

# Open WebUI Cloud Run instance
openwebui_cr_service = gcp.cloudrun.Service(
    "openwebui-service",
    location=gcp_region,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            containers=[
                gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                    image="ollama/ollama",
                    envs=[
                        ServiceTemplateSpecContainerEnvArgs(
                            name="OLLAMA_BASE_URL",
                            value=ollama_url,
                        ),
                        ServiceTemplateSpecContainerEnvArgs(
                            name="WEBUI_AUTH",
                            value='false',
                        )
                    ],
                )
            ],
        ),
    ),
    traffics=[
        gcp.cloudrun.ServiceTrafficArgs(
            latest_revision=True,
            percent=100,
        )
    ],
    opts=pulumi.ResourceOptions(depends_on=[ollama_cr_service])
)


pulumi.export("ollama_url", ollama_cr_service.uri)
#pulumi.export("open_webui_url", openwebui_cr_service.statuses[0].url)