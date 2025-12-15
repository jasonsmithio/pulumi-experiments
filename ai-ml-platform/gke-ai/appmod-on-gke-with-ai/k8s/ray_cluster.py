import pulumi
import pulumi_kubernetes as k8s
from typing import Optional, Dict, Any, List

class RayCluster(pulumi.ComponentResource):
    def __init__(self,
                 name: str,
                 ray_version: str = "2.37.0",
                 head_cpu: str = "2",
                 head_memory: str = "4Gi",
                 worker_replicas: int = 1,
                 worker_cpu: str = "2",
                 worker_memory: str = "4Gi",
                 namespace: Optional[str] = None,
                 opts: Optional[pulumi.ResourceOptions] = None):
        """
        A custom component resource for deploying a KubeRay RayCluster.
        
        :param name: The name of the resource.
        :param ray_version: The version of the Ray image to use.
        :param head_cpu: CPU request/limit for the head node.
        :param head_memory: Memory request/limit for the head node.
        :param worker_replicas: Initial number of worker replicas.
        :param worker_cpu: CPU request/limit for the worker nodes.
        :param worker_memory: Memory request/limit for the worker nodes.
        :param namespace: Kubernetes namespace to deploy into.
        :param opts: standard Pulumi ResourceOptions.
        """
        super().__init__('custom:app:RayCluster', name, None, opts)

        # Standard metadata for the K8s object
        metadata = k8s.meta.v1.ObjectMetaArgs(
            name=name,
            namespace=namespace,
        )

        # Define the arguments for the CustomResource
        self.cluster = k8s.apiextensions.CustomResource(
            f"{name}-cr",
            api_version="ray.io/v1",
            kind="RayCluster",
            metadata=metadata,
            spec={
                "rayVersion": ray_version,
                "headGroupSpec": {
                    "rayStartParams": {
                        "dashboard-host": "0.0.0.0"
                    },
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "ray-head",
                                "image": f"rayproject/ray:{ray_version}",
                                "ports": [
                                    {"containerPort": 6379, "name": "gcs"},
                                    {"containerPort": 8265, "name": "dashboard"},
                                    {"containerPort": 10001, "name": "client"},
                                ],
                                "resources": {
                                    "limits": {
                                        "cpu": head_cpu,
                                        "ephemeral-storage": "9Gi",
                                        "memory": head_memory
                                    },
                                    "requests": {
                                        "cpu": head_cpu,
                                        "ephemeral-storage": "9Gi",
                                        "memory": head_memory
                                    }
                                }
                            }]
                        }
                    }
                },
                "workerGroupSpecs": [{
                    "replicas": worker_replicas,
                    "minReplicas": 1,
                    "maxReplicas": 5,
                    "groupName": "worker-group",
                    "rayStartParams": {},
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "ray-worker",
                                "image": f"rayproject/ray:{ray_version}",
                                "resources": {
                                    "limits": {
                                        "cpu": worker_cpu,
                                        "ephemeral-storage": "9Gi",
                                        "memory": worker_memory
                                    },
                                    "requests": {
                                        "cpu": worker_cpu,
                                        "ephemeral-storage": "9Gi",
                                        "memory": worker_memory
                                    }
                                }
                            }]
                        }
                    }
                }]
            },
            opts=pulumi.ResourceOptions(parent=self) # Set the parent to 'self'
        )

        # Register outputs so they are visible on the CLI
        self.register_outputs({
            "name": name,
            "ray_version": ray_version,
            "dashboard_url": pulumi.Output.concat("http://", name, "-head-svc:8265") # Note: KubeRay creates a service named <cluster-name>-head-svc
        })