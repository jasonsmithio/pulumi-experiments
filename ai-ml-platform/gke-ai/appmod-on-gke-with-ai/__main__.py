import pulumi
import pulumi_gcp as gcp
import pulumi_kubernetes as kubernetes
from ray_cluster import RayCluster

# Get some provider-namespaced configuration values
gconfig = pulumi.Config("gcp")
gcp_project = gconfig.require("project")
gcp_region = gconfig.get("region", "us-central1")
gcp_zone = gconfig.get("zone", "us-central1-a")
gke_network = gconfig.get("gkeNetwork", "default")
gke_cluster_name = gconfig.get("clusterName", "ray-cluster")
gke_master_version = gconfig.get("master_version", 1.29)
gke_master_node_count = gconfig.get_int("nodesPerZone", 1)

#setting unique values for the nodepool
gpu_nodepool_name = gconfig.get("nodepoolName", "ray-gpu-nodepool")
gpu_nodepool_node_count = gconfig.get_int("nodesPerZone", 2)
gpu_ml_machine_type = gconfig.get("mlMachines", "g2-standard-24")

# Create a cluster in the new network and subnet
gke_cluster = gcp.container.Cluster("ray-cluster", 
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
    workload_identity_config=gcp.container.ClusterWorkloadIdentityConfigArgs(
        workload_pool=str(gcp_project)+".svc.id.goog",
    ),
    addons_config=gcp.container.ClusterAddonsConfigArgs(
        gcs_fuse_csi_driver_config={
            "enabled": "True",
        },
    ),
    node_config=gcp.container.ClusterNodeConfigArgs(
        oauth_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        shielded_instance_config={
            "enable_secure_boot" : "True",
            "enable_integrity_monitoring": "True",
        },
    ),
)

# Defining the GKE Node Pool
gpu_nodepool = gcp.container.NodePool("gpu-nodepool",
    name = gpu_nodepool_name,
    location = gcp_region,
    node_locations = [gcp_zone],
    cluster = gke_cluster.id,
    node_count = gpu_nodepool_node_count,
    node_config = gcp.container.NodePoolNodeConfigArgs(
        preemptible = False,
        machine_type = gpu_ml_machine_type,
        disk_size_gb = 20,
        ephemeral_storage_local_ssd_config={
            "local_ssd_count":"2",
        },
        guest_accelerators=[gcp.container.NodePoolNodeConfigGuestAcceleratorArgs(
            type="nvidia-l4",
            count=2,
            gpu_driver_installation_config={
                "gpu_driver_version" : "LATEST",
            },
        )],
        metadata = {
            "install-nvidia-driver": "True",
        },
        oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"],
        shielded_instance_config = gcp.container.NodePoolNodeConfigShieldedInstanceConfigArgs(
            enable_integrity_monitoring = True,
            enable_secure_boot = True
        )
    ),
    # Set the Nodepool Autoscaling configuration
    autoscaling = gcp.container.NodePoolAutoscalingArgs(
        min_node_count = 1,
        max_node_count = 2
    ),
    # Set the Nodepool Management configuration
    management = gcp.container.NodePoolManagementArgs(
        auto_repair  = True,
        auto_upgrade = True
    )
)

# System Node Pool for non-GPU workloads
system_nodepool = gcp.container.NodePool("system-nodepool",
    name = "system-pool",
    location = gcp_region,
    node_locations = [gcp_zone],
    cluster = gke_cluster.id,
    initial_node_count = 1,
    node_config = gcp.container.NodePoolNodeConfigArgs(
        machine_type = "e2-standard-4",
        disk_size_gb = 50,
        oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"],
        shielded_instance_config = gcp.container.NodePoolNodeConfigShieldedInstanceConfigArgs(
            enable_integrity_monitoring = True,
            enable_secure_boot = True
        )
    ),
    autoscaling = gcp.container.NodePoolAutoscalingArgs(
        min_node_count = 1,
        max_node_count = 2
    ),
    management = gcp.container.NodePoolManagementArgs(
        auto_repair  = True,
        auto_upgrade = True
    )
)

# Manufacture a GKE-style Kubeconfig. Note that this is slightly "different" because of the way GKE requires
# gcloud to be in the picture for cluster authentication (rather than using the client cert/key directly).
k8s_info = pulumi.Output.all(gke_cluster.name, gke_cluster.endpoint, gke_cluster.master_auth)
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
# We depend on system_nodepool too to ensure cluster is ready for system pods
kubeconfig = kubernetes.Provider('gke_k8s', kubeconfig=k8s_config, opts=pulumi.ResourceOptions(depends_on=[gpu_nodepool, system_nodepool]))

# Create a dedicated namespace for Ray system components
ray_system_ns = kubernetes.core.v1.Namespace("ray-system",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="ray-system",
    ),
    opts=pulumi.ResourceOptions(provider=kubeconfig)
)

# Deploy KubeRay Operator
ray_operator = kubernetes.helm.v3.Release("kuberay-operator",
    args=kubernetes.helm.v3.ReleaseArgs(
        chart="kuberay-operator",
        version="1.2.2",
        repository_opts=kubernetes.helm.v3.RepositoryOptsArgs(
            repo="https://ray-project.github.io/kuberay-helm/",
        ),
        namespace=ray_system_ns.metadata.name,
        values={
            "nodeSelector": {
                "cloud.google.com/gke-nodepool": "system-pool"
            }
        }
    ),
    opts=pulumi.ResourceOptions(provider=kubeconfig)
)

# Instantiate the Ray Cluster component
pytorch_cluster = RayCluster(
    "pytorch-mnist-cluster",
    ray_version="2.37.0",
    worker_replicas=4,
    head_cpu="2",
    head_memory="4Gi",
    worker_cpu="4",
    worker_memory="8Gi"
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

# Retrieve the Hugging Face Token from GCP Secret Manager
# We fetch the latest version of the secret to inject into K8s
hf_secret_version = gcp.secretmanager.get_secret_version_access(
    secret="hf-secret-key",
    version="latest",
    project=gcp_project
)

# Create Kubernetes Secret with the HF token
k8s_hf_secret = kubernetes.core.v1.Secret("hf-secret",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="hf-secret",
        namespace="default",
    ),
    string_data={
        "hf_api_token": hf_secret_version.secret_data,
    },
    type="Opaque",
    opts=pulumi.ResourceOptions(provider=kubeconfig)
)

deploy = mixtral(kubeconfig)

# Get GCP Secret with Hugging Face Key (for IAM binding reference)
hf_secret = gcp.secretmanager.get_secret(secret_id="hf-secret-key")

# IAM Bindings for Workload Identity
# We allow the K8s Service Account to access the GCP Secret
hf_sa_binding = gcp.secretmanager.SecretIamBinding("binding",
    secret_id=hf_secret.id,
    role="roles/secretmanager.secretAccessor",
    members=[pulumi.Output.format("principal://iam.googleapis.com/projects/{0}/locations/global/workloadIdentityPools/{0}.svc.id.goog/subject/ns/default/sa/{1}", gcp_project, hf_service_account.metadata['name'])]
)

service = deploy.mixtralService()
deployment = deploy.mixtral8x7b()

# Export the Service's IP address
service_ip = service.status.apply(
    lambda status: status.load_balancer.ingress[0].ip if status.load_balancer.ingress else None
)

pulumi.export('service_ip', service_ip)
pulumi.export("clusterName", gke_cluster.name)
pulumi.export("clusterId", gke_cluster.id)
# Export the presumed dashboard URL
pulumi.export("ray_dashboard", pytorch_cluster.dashboard_url)
pulumi.export("service_account_name", hf_service_account.metadata['name'])
