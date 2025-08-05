import pulumi
import pulumi_gcp as gcp
import pulumi_kubernetes as kubernetes
from pulumi_kubernetes.yaml import ConfigFile
#from k8s.mixtral import Mixtral as mixtral

# Get some provider-namespaced configuration values
gconfig = pulumi.Config()
gcp_project = pulumi.Config("gcp").require("project")
gcp_region = pulumi.Config("gcp").get("region", "us-central1")
gcp_zone = gconfig.get("zone", "us-central1-a")
gke_network = gconfig.get("gkeNetwork", "default")
gke_cluster_name = gconfig.get("clusterName", "axion-cluster")
gke_master_version = gconfig.get("master_version", 1.31)
gke_master_node_count = gconfig.get_int("nodesPerZone", 2)

#setting unique values for the nodepool
gke_nodepool_name = gconfig.get("nodepoolName", "axion-nodepool")
gke_nodepool_node_count = gconfig.get_int("nodesPerZone", 2)
gke_ml_machine_type = gconfig.get("mlMachines", "c4a-standard-64")

# Create a cluster in the new network and subnet
gke_cluster = gcp.container.Cluster("axion-cluster-1", 
    name = gke_cluster_name,
    deletion_protection=False,
    location = gcp_region,
    network = gke_network,
    networking_mode="VPC_NATIVE",
    initial_node_count = gke_master_node_count,
    remove_default_node_pool = True,
    min_master_version = gke_master_version,
    secret_manager_config=gcp.container.ClusterSecretManagerConfigArgs(
        enabled=True,
    ),
    enable_intranode_visibility=True,
    workload_identity_config=gcp.container.ClusterWorkloadIdentityConfigArgs(
        workload_pool=str(gcp_project)+".svc.id.goog",
    ),
    gateway_api_config=gcp.container.ClusterGatewayApiConfigArgs(
        channel="CHANNEL_STANDARD"
    ),
    addons_config=gcp.container.ClusterAddonsConfigArgs(
        gcs_fuse_csi_driver_config={
            "enabled": True,
        },
        gce_persistent_disk_csi_driver_config=gcp.container.ClusterAddonsConfigGcePersistentDiskCsiDriverConfigArgs(
            enabled=True,
        ),
        ray_operator_configs={
            "enabled": True,
            "ray_cluster_logging_config": {
                "enabled": True,
            },
            "ray_cluster_monitoring_config": {
                "enabled": True,
            },
        },
        # Enabling HTTP/HTTPS Load Balancing addon necessary for Gateway
        http_load_balancing=gcp.container.ClusterAddonsConfigHttpLoadBalancingArgs(
            disabled=False,
        ),
    ),
    node_config=gcp.container.ClusterNodeConfigArgs(
        oauth_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        shielded_instance_config={
            "enable_secure_boot" : True,
            "enable_integrity_monitoring": True,
        },
    ),
)

# Defining the GKE Node Pool
gke_nodepool = gcp.container.NodePool("axion-nodepool-1",
    name = gke_nodepool_name,
    location = gcp_region,
    node_locations = [gcp_zone],
    cluster = gke_cluster.id,
    node_count = gke_nodepool_node_count,
    node_config = gcp.container.NodePoolNodeConfigArgs(
        preemptible = False,
        machine_type = gke_ml_machine_type,
        disk_size_gb = 20,
        oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"],
        shielded_instance_config = gcp.container.NodePoolNodeConfigShieldedInstanceConfigArgs(
            enable_integrity_monitoring = True,
            enable_secure_boot = True
        )
    ),
    # Set the Nodepool Autoscaling configuration
    autoscaling = gcp.container.NodePoolAutoscalingArgs(
        min_node_count = 1,
        max_node_count = 8
    ),
    # Set the Nodepool Management configuration
    management = gcp.container.NodePoolManagementArgs(
        auto_repair  = True,
        auto_upgrade = True
    ),
    opts=pulumi.ResourceOptions(depends_on=[gke_cluster])
)

# Manufacture a GKE-style Kubeconfig. Note that this is slightly "different" because of the way GKE requires
# gcloud to be in the picture for cluster authentication (rather than using the client cert/key directly).
k8s_info = pulumi.Output.all(gke_cluster.name, gke_cluster.endpoint, gke_cluster.master_auth)
#k8s_info = 
k8s_config = k8s_info.apply(
    lambda info: """apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: {0}
    server: https://{1}
  name: {2}
contexts:
- context:
    cluster: {2}
    user: {2}
  name: {2}
current-context: {2}
kind: Config
preferences: {{}}
users:
- name: {2}
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      command: gke-gcloud-auth-plugin
      installHint: Install gke-gcloud-auth-plugin for use with kubectl by following
        https://cloud.google.com/blog/products/containers-kubernetes/kubectl-auth-changes-in-gke
      provideClusterInfo: true
""".format(info[2]['cluster_ca_certificate'], info[1], '{0}_{1}_{2}'.format(gcp_project, gcp_zone, info[0])))

# Make a Kubernetes provider instance that uses our cluster from above.
kubeconfig = kubernetes.Provider('gke-k8s', kubeconfig=k8s_config, opts=pulumi.ResourceOptions(depends_on=[gke_cluster]))

# Create a GCP service account for the nodepool
gke_nodepool_sa = gcp.serviceaccount.Account(
    "gke-nodepool-sa",
    account_id=pulumi.Output.concat(gke_cluster.name, "-np-1-sa"),
    display_name="Nodepool 1 Service Account",
    #opts=pulumi.ResourceOptions(provider=gke_cluster)
    #depends_on=[gke_cluster]
)

# Create a ServiceAccount in a Kubernetes cluster for default namespace
hf_service_account = kubernetes.core.v1.ServiceAccount("k8s-sa",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        namespace="default",
        name="hf-sa"
    ),
    automount_service_account_token=True,
    opts=pulumi.ResourceOptions(provider=kubeconfig)
)

# Hugging Face key as a Kubernetes Secret
hf_token = gcp.secretmanager.get_secret(secret_id="hf-secret-key")


# Create a Kubernetes Secret
hfs_k8s_secret = kubernetes.core.v1.Secret(
    "hf-k8s-secret",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="hf-secret",
        namespace="default"
    ),
    string_data={
        "hf_api_token": str(hf_token)
    },
    opts=pulumi.ResourceOptions(provider=kubeconfig)
)

# Apply vLLM K8s YAML

#vllm_yaml = ConfigFile(
#    "vllm_yaml",
#    file="k8s/vllm-3-4b-it.yaml",
#    opts=pulumi.ResourceOptions(provider=kubeconfig)
#)

#sdxl_yaml = ConfigFile(
#    "sdxl_yaml",
#    file="k8s/serve_sdxl_v5e.yaml",
#    opts=pulumi.ResourceOptions(provider=kubeconfig)
#)

sc_yaml = ConfigFile(
    "hyperdisk-arm-sc-yaml",
    file="k8s/hyperdisk-arm-sc.yaml",
    opts=pulumi.ResourceOptions(provider=kubeconfig)
)

ollama_yaml = ConfigFile(
    "ollama-yaml",
    file="k8s/ollama-stable-diffusion.yaml",
    opts=pulumi.ResourceOptions(provider=kubeconfig,depends_on=[sc_yaml])
)


#deploy = mixtral(kubeconfig)

# Get GCP Secret with Hugging Face Key
#hf_secret = gcp.secretmanager.get_secret(secret_id="hf-secret-key")

# IAM Bindings
#ray_sa_binding = gcp.secretmanager.SecretIamBinding("binding",
#    #project=hf_secret["project"],
#    secret_id=hf_secret.id,
#    #secret_id="hf-secret-key",
#    role="roles/secretmanager.secretAccessor",
#    members=["principal://iam.googleapis.com/projects/"+str(gcp_project)+"/locations/global/workloadIdentityPools/"#+str(gcp_project)+".svc.id.goog/subject/ns/default/sa/"+str(hf_service_account.metadata['name'])])

#pulumi.export("service_account_name", ray_service_account.metadata["name"])

#service = deploy.mixtralService()
#deployment = deploy.mixtral8x7b()

# Export the Service's IP address
#service_ip = service.status.apply(
#    lambda status: status.load_balancer.ingress[0].ip if status.load_balancer.ingress else None
#)

#pulumi.export('service_ip', service_ip)
pulumi.export("clusterName", gke_cluster.name)
pulumi.export("clusterId", gke_cluster.id)
