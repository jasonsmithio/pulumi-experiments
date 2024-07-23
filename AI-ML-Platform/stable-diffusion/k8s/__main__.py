import pulumi
import pulumi_kubernetes as kubernetes

stable_diffusion_deployment_final = kubernetes.apps.v1.Deployment("stableDiffusionDeploymentFinal",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        labels={
            "app": "stable-diffusion",
        },
        name="stable-diffusion-deployment-final",
    ),
    spec=kubernetes.apps.v1.DeploymentSpecArgs(
        replicas=1,
        selector=kubernetes.meta.v1.LabelSelectorArgs(
            match_labels={
                "app": "stable-diffusion",
            },
        ),
        template=kubernetes.core.v1.PodTemplateSpecArgs(
            metadata=kubernetes.meta.v1.ObjectMetaArgs(
                labels={
                    "app": "stable-diffusion",
                },
            ),
            spec=kubernetes.core.v1.PodSpecArgs(
                containers=[kubernetes.core.v1.ContainerArgs(
                    args=["source /runtime-lib/bin/activate; cp /user-watch.py /runtime-lib/stable-diffusion-webui/user-watch.py; cp /start.sh /runtime-lib/stable-diffusion-webui/start.sh; cd /runtime-lib/stable-diffusion-webui; python3 launch.py --listen --xformers --enable-insecure-extension-access --no-gradio-queue"],
                    command=[
                        "/bin/bash",
                        "-c",
                    ],
                    env=[kubernetes.core.v1.EnvVarArgs(
                        name="MY_NODE_NAME",
                        value_from=kubernetes.core.v1.EnvVarSourceArgs(
                            field_ref=kubernetes.core.v1.ObjectFieldSelectorArgs(
                                field_path="spec.nodeName",
                            ),
                        ),
                    )],
                    image="us-central1-docker.pkg.dev/flius-vpc-2/stable-diffusion-repo/sd-webui-final:0.1",
                    image_pull_policy="Always",
                    name="stable-diffusion-webui",
                    ports=[kubernetes.core.v1.ContainerPortArgs(
                        container_port=7860,
                    )],
                    resources=kubernetes.core.v1.ResourceRequirementsArgs(
                        limits={
                            "nvidia.com/gpu": "1",
                        },
                    ),
                    volume_mounts=[kubernetes.core.v1.VolumeMountArgs(
                        mount_path="/runtime-lib",
                        name="runtime-lib",
                    )],
                )],
                node_selector={
                    "iam.gke.io/gke-metadata-server-enabled": "true",
                },
                service_account_name="workload-identity-ksa",
                volumes=[kubernetes.core.v1.VolumeArgs(
                    host_path=kubernetes.core.v1.HostPathVolumeSourceArgs(
                        path="/var/lib/runtime-lib",
                    ),
                    name="runtime-lib",
                )],
            ),
        ),
    ))


sd_ds_init_disk = kubernetes.apps.v1.DaemonSet("sdDsInitDisk",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        labels={
            "app": "sd-ds-init-disk",
        },
        name="sd-ds-init-disk",
    ),
    spec=kubernetes.apps.v1.DaemonSetSpecArgs(
        selector=kubernetes.meta.v1.LabelSelectorArgs(
            match_labels={
                "app": "sd-ds-init-disk",
            },
        ),
        template=kubernetes.core.v1.PodTemplateSpecArgs(
            metadata=kubernetes.meta.v1.ObjectMetaArgs(
                labels={
                    "app": "sd-ds-init-disk",
                },
            ),
            spec=kubernetes.core.v1.PodSpecArgs(
                affinity=kubernetes.core.v1.AffinityArgs(
                    node_affinity=kubernetes.core.v1.NodeAffinityArgs(
                        required_during_scheduling_ignored_during_execution=kubernetes.core.v1.NodeSelectorArgs(
                            node_selector_terms=[kubernetes.core.v1.NodeSelectorTermArgs(
                                match_expressions=[kubernetes.core.v1.NodeSelectorRequirementArgs(
                                    key="cloud.google.com/gke-accelerator",
                                    operator="Exists",
                                )],
                            )],
                        ),
                    ),
                ),
                containers=[kubernetes.core.v1.ContainerArgs(
                    env=[kubernetes.core.v1.EnvVarArgs(
                        name="STARTUP_SCRIPT",
                        value="""#!/bin/bash
set -euo pipefail

if [ ! -f  /var/lib/runtime-lib/added-disk.txt ]
then
  mkdir -p /var/lib/runtime-lib
  mount -o discard,defaults /dev/sdb /var/lib/runtime-lib
  sleep 10
  touch /var/lib/runtime-lib/added-disk.txt
fi
""",
                    )],
                    image="gcr.io/google-containers/startup-script:v2",
                    image_pull_policy="Always",
                    name="sd-ds-init-disk",
                    security_context=kubernetes.core.v1.SecurityContextArgs(
                        privileged=True,
                    ),
                )],
                host_pid=True,
                init_containers=[kubernetes.core.v1.ContainerArgs(
                    args=["/attach-disk.sh"],
                    command=[
                        "bash",
                        "-c",
                    ],
                    env=[
                        kubernetes.core.v1.EnvVarArgs(
                            name="MY_NODE_NAME",
                            value_from=kubernetes.core.v1.EnvVarSourceArgs(
                                field_ref=kubernetes.core.v1.ObjectFieldSelectorArgs(
                                    field_path="spec.nodeName",
                                ),
                            ),
                        ),
                        kubernetes.core.v1.EnvVarArgs(
                            name="IMAGE_NAME",
                            value="sd-image",
                        ),
                    ],
                    image="us-central1-docker.pkg.dev/flius-vpc-2/stable-diffusion-repo/attach-disk-image",
                    image_pull_policy="Always",
                    name="init-disk",
                )],
                node_selector={
                    "iam.gke.io/gke-metadata-server-enabled": "true",
                },
                tolerations=[kubernetes.core.v1.TolerationArgs(
                    operator="Exists",
                )],
            ),
        ),
    ))
