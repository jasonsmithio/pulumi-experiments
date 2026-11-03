import pulumi
import pulumi_gcp as gcp
import pulumi_kubernetes as kubernetes
import pulumi_docker_build as docker_build
from pulumi_kubernetes.yaml import ConfigFile

# Load Pulumi configuration
gconfig = pulumi.Config()
gcp_config = pulumi.Config("gcp")
gcp_project = gcp_config.require("project")
gcp_region = gcp_config.get("region") or "us-central1"
gcp_zone = gcp_config.get("zone") or gconfig.get("zone") or f"{gcp_region}-a"

gke_network = gconfig.get("gkeNetwork") or "default"
gke_cluster_name = gconfig.get("clusterName") or "axion-cluster"
gke_master_version = gconfig.get("master_version") or "1.31"
gke_nodepool_name = gconfig.get("nodepoolName") or "axion-nodepool"
gke_nodepool_node_count = gconfig.get_int("nodesPerZone") or gconfig.get_int("node_count") or 2
gke_ml_machine_type = (
    gconfig.get("mlMachines")
    or gconfig.get("node_machine_type")
    or "c4a-standard-16"
)
ollama_model = gconfig.get("ollamaModel") or "gemma4:4b-highthread"

# 1. Create a VPC-native GKE Cluster with Hyperdisk CSI & Gateway API enabled
gke_cluster = gcp.container.Cluster(
    "axion-cluster-1",
    name=gke_cluster_name,
    deletion_protection=False,
    location=gcp_region,
    network=gke_network,
    networking_mode="VPC_NATIVE",
    initial_node_count=1,
    remove_default_node_pool=True,
    min_master_version=str(gke_master_version),
    secret_manager_config=gcp.container.ClusterSecretManagerConfigArgs(
        enabled=True,
    ),
    enable_intranode_visibility=True,
    workload_identity_config=gcp.container.ClusterWorkloadIdentityConfigArgs(
        workload_pool=f"{gcp_project}.svc.id.goog",
    ),
    gateway_api_config=gcp.container.ClusterGatewayApiConfigArgs(
        channel="CHANNEL_STANDARD",
    ),
    addons_config=gcp.container.ClusterAddonsConfigArgs(
        gcs_fuse_csi_driver_config=gcp.container.ClusterAddonsConfigGcsFuseCsiDriverConfigArgs(
            enabled=True,
        ),
        gce_persistent_disk_csi_driver_config=gcp.container.ClusterAddonsConfigGcePersistentDiskCsiDriverConfigArgs(
            enabled=True,
        ),
        http_load_balancing=gcp.container.ClusterAddonsConfigHttpLoadBalancingArgs(
            disabled=False,
        ),
    ),
    node_config=gcp.container.ClusterNodeConfigArgs(
        oauth_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        shielded_instance_config=gcp.container.ClusterNodeConfigShieldedInstanceConfigArgs(
            enable_secure_boot=True,
            enable_integrity_monitoring=True,
        ),
    ),
)

# 2. Create the Google Axion Arm64 (C4A) GKE Node Pool
# Note: C4A VMs require hyperdisk-balanced boot disks.
gke_nodepool = gcp.container.NodePool(
    "axion-nodepool-1",
    name=gke_nodepool_name,
    location=gcp_region,
    node_locations=[gcp_zone],
    cluster=gke_cluster.id,
    node_count=gke_nodepool_node_count,
    node_config=gcp.container.NodePoolNodeConfigArgs(
        preemptible=False,
        machine_type=gke_ml_machine_type,
        disk_type="hyperdisk-balanced",
        disk_size_gb=50,
        oauth_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        shielded_instance_config=gcp.container.NodePoolNodeConfigShieldedInstanceConfigArgs(
            enable_integrity_monitoring=True,
            enable_secure_boot=True,
        ),
    ),
    autoscaling=gcp.container.NodePoolAutoscalingArgs(
        min_node_count=1,
        max_node_count=8,
    ),
    management=gcp.container.NodePoolManagementArgs(
        auto_repair=True,
        auto_upgrade=True,
    ),
    opts=pulumi.ResourceOptions(depends_on=[gke_cluster]),
)

# 3. Manufacture a GKE-style Kubeconfig for the Pulumi Kubernetes Provider
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
""".format(
        info[2]["cluster_ca_certificate"],
        info[1],
        f"{gcp_project}_{gcp_zone}_{info[0]}",
    )
)

kubeconfig = kubernetes.Provider(
    "gke-k8s",
    kubeconfig=k8s_config,
    opts=pulumi.ResourceOptions(depends_on=[gke_cluster, gke_nodepool]),
)

# 4. Provision the Hyperdisk Balanced Arm StorageClass & Ollama + Gemma 4 StatefulSet
sc_yaml = ConfigFile(
    "hyperdisk-arm-sc-yaml",
    file="k8s/hyperdisk-arm-sc.yaml",
    opts=pulumi.ResourceOptions(provider=kubeconfig, depends_on=[gke_nodepool]),
)

ollama_yaml = ConfigFile(
    "ollama-gemma4-yaml",
    file="k8s/ollama-gemma4.yaml",
    opts=pulumi.ResourceOptions(provider=kubeconfig, depends_on=[sc_yaml]),
)

# 5. Artifact Registry Repository & Multi-Arch (linux/amd64, linux/arm64) Streamlit Image
streamlit_image_repo = gcp.artifactregistry.Repository(
    "streamlit-repo",
    location=gcp_region,
    repository_id="streamlit",
    description="Multi-arch Artifact Registry repo for the KubeCon Axion Gemma 4 Streamlit UI",
    format="DOCKER",
    docker_config=gcp.artifactregistry.RepositoryDockerConfigArgs(
        immutable_tags=False,
    ),
)

streamlit_image_uri = f"{gcp_region}-docker.pkg.dev/{gcp_project}/streamlit/axion-gemma4-ui:latest"

docker_image = docker_build.Image(
    "streamlit-gemma4-image",
    tags=[streamlit_image_uri],
    context=docker_build.BuildContextArgs(
        location="./streamlit/",
    ),
    platforms=[
        docker_build.Platform.LINUX_AMD64,
        docker_build.Platform.LINUX_ARM64,
    ],
    push=True,
    opts=pulumi.ResourceOptions(depends_on=[streamlit_image_repo]),
)

# 6. Provision Least-Privilege Read-Only RBAC for the Google ADK GKE SRE & FinOps Agent
sre_agent_sa = kubernetes.core.v1.ServiceAccount(
    "axion-sre-agent-sa",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="axion-sre-agent-sa",
        namespace="default",
    ),
    opts=pulumi.ResourceOptions(provider=kubeconfig, depends_on=[gke_nodepool]),
)

sre_agent_role = kubernetes.rbac.v1.ClusterRole(
    "axion-sre-agent-reader",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="axion-sre-agent-reader",
    ),
    rules=[
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=[""],
            resources=["nodes", "pods", "services", "persistentvolumeclaims"],
            verbs=["get", "list", "watch"],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=["apps"],
            resources=["deployments", "statefulsets"],
            verbs=["get", "list", "watch"],
        ),
    ],
    opts=pulumi.ResourceOptions(provider=kubeconfig, depends_on=[gke_nodepool]),
)

sre_agent_binding = kubernetes.rbac.v1.ClusterRoleBinding(
    "axion-sre-agent-binding",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="axion-sre-agent-binding",
    ),
    role_ref=kubernetes.rbac.v1.RoleRefArgs(
        api_group="rbac.authorization.k8s.io",
        kind="ClusterRole",
        name=sre_agent_role.metadata.name,
    ),
    subjects=[
        kubernetes.rbac.v1.SubjectArgs(
            kind="ServiceAccount",
            name=sre_agent_sa.metadata.name,
            namespace="default",
        )
    ],
    opts=pulumi.ResourceOptions(provider=kubeconfig, depends_on=[sre_agent_sa, sre_agent_role]),
)

# 7. Deploy the Google ADK + Streamlit Agent UI in-cluster on the GKE Axion Arm64 Node Pool
streamlit_labels = {
    "app": "streamlit-gemma4-ui",
    "ai.gke.io/model": "gemma-4-4b",
    "ai.gke.io/agent-framework": "google-adk",
}

streamlit_deployment = kubernetes.apps.v1.Deployment(
    "streamlit-gemma4-ui",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="streamlit-gemma4-ui",
        namespace="default",
        labels=streamlit_labels,
    ),
    spec=kubernetes.apps.v1.DeploymentSpecArgs(
        replicas=1,
        selector=kubernetes.meta.v1.LabelSelectorArgs(
            match_labels={"app": "streamlit-gemma4-ui"},
        ),
        template=kubernetes.core.v1.PodTemplateSpecArgs(
            metadata=kubernetes.meta.v1.ObjectMetaArgs(
                labels=streamlit_labels,
            ),
            spec=kubernetes.core.v1.PodSpecArgs(
                service_account_name=sre_agent_sa.metadata.name,
                affinity=kubernetes.core.v1.AffinityArgs(
                    node_affinity=kubernetes.core.v1.NodeAffinityArgs(
                        required_during_scheduling_ignored_during_execution=kubernetes.core.v1.NodeSelectorArgs(
                            node_selector_terms=[
                                kubernetes.core.v1.NodeSelectorTermArgs(
                                    match_expressions=[
                                        kubernetes.core.v1.NodeSelectorRequirementArgs(
                                            key="kubernetes.io/arch",
                                            operator="In",
                                            values=["arm64"],
                                        )
                                    ]
                                )
                            ]
                        )
                    )
                ),
                node_selector={
                    "cloud.google.com/gke-nodepool": gke_nodepool_name,
                },
                containers=[
                    kubernetes.core.v1.ContainerArgs(
                        name="streamlit",
                        image=docker_image.ref,
                        ports=[
                            kubernetes.core.v1.ContainerPortArgs(
                                container_port=8080,
                                name="http",
                            )
                        ],
                        env=[
                            kubernetes.core.v1.EnvVarArgs(
                                name="OLLAMA_BASE_URL",
                                value="http://ollama-service:11434/v1",
                            ),
                            kubernetes.core.v1.EnvVarArgs(
                                name="OLLAMA_MODEL",
                                value=ollama_model,
                            ),
                            kubernetes.core.v1.EnvVarArgs(
                                name="AXION_MACHINE_TYPE",
                                value=gke_ml_machine_type,
                            ),
                            kubernetes.core.v1.EnvVarArgs(
                                name="GKE_CLUSTER_NAME",
                                value=gke_cluster_name,
                            ),
                        ],
                        resources=kubernetes.core.v1.ResourceRequirementsArgs(
                            requests={"cpu": "500m", "memory": "1Gi"},
                            limits={"cpu": "1", "memory": "2Gi"},
                        ),
                    )
                ],
            ),
        ),
    ),
    opts=pulumi.ResourceOptions(
        provider=kubeconfig,
        depends_on=[ollama_yaml, docker_image, sre_agent_binding],
    ),
)

streamlit_service = kubernetes.core.v1.Service(
    "streamlit-gemma4-service",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="streamlit-gemma4-service",
        namespace="default",
        labels=streamlit_labels,
    ),
    spec=kubernetes.core.v1.ServiceSpecArgs(
        type="LoadBalancer",
        selector={"app": "streamlit-gemma4-ui"},
        ports=[
            kubernetes.core.v1.ServicePortArgs(
                protocol="TCP",
                port=80,
                target_port=8080,
            )
        ],
    ),
    opts=pulumi.ResourceOptions(
        provider=kubeconfig,
        depends_on=[streamlit_deployment],
    ),
)

streamlit_ip = streamlit_service.status.apply(
    lambda status: (
        status.load_balancer.ingress[0].ip
        if status and status.load_balancer and status.load_balancer.ingress
        else "Pending"
    )
)

pulumi.export("clusterName", gke_cluster.name)
pulumi.export("clusterId", gke_cluster.id)
pulumi.export("axionMachineType", gke_ml_machine_type)
pulumi.export("ollamaModel", ollama_model)
pulumi.export("streamlitImage", docker_image.ref)
pulumi.export("streamlitIp", streamlit_ip)
pulumi.export("streamlitUrl", streamlit_ip.apply(lambda ip: f"http://{ip}"))
