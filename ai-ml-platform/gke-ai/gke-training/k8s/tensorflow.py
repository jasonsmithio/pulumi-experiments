import pulumi
import pulumi_kubernetes as kubernetes

class Tensorflow:

    def __init__(self, bucket, k8s_sa, provider):
        self.bucket = bucket
        self.k8s_sa = k8s_sa
        self.provider = provider

    def test_tensorflow_pod(self):
        deployment = kubernetes.core.v1.Pod("testTensorflowPod",
            metadata={
                "annotations": {
                    "gke-gcsfuse/volumes": "true",
                },
                "name": "test-tensorflow-pod",
            },
            spec={
                "containers": [{
                    "args": ["while true; do sleep infinity; done;"],
                    "command": [
                        "/bin/bash",
                        "-c",
                        "--",
                    ],
                    "image": "tensorflow/tensorflow:latest-gpu",
                    "name": "tensorflow",
                    "resources": {
                        "limits": {
                            "nvidia.com/gpu": "1",
                        },
                    },
                    "volume_mounts": [{
                        "mount_path": "/data",
                        "name": "gcs-fuse-csi-vol",
                        "read_only": False,
                    }],
                }],
                "node_selector": {
                    "cloud.google.com/gke-accelerator": "nvidia-tesla-t4",
                },
                "service_account_name": self.k8s_sa,
                "tolerations": [{
                    "effect": "NoSchedule",
                    "key": "nvidia.com/gpu",
                    "operator": "Exists",
                }],
                "volumes": [{
                    "csi": {
                        "driver": "gcsfuse.csi.storage.gke.io",
                        "read_only": False,
                        "volume_attributes": {
                            "bucketName": self.bucket,
                            "mountOptions": "implicit-dirs",
                        },
                    },
                    "name": "gcs-fuse-csi-vol",
                }],
            })
        
        return deployment
    
    def tensorflow_mnist(self):
        mnist_training_job = kubernetes.batch.v1.Job("mnistTrainingJob",
            metadata={
                "name": "mnist-training-job",
            },
            spec={
                "template": {
                    "metadata": {
                        "annotations": {
                            "gke-gcsfuse/volumes": "true",
                        },
                        "name": "mnist",
                    },
                    "spec": {
                        "containers": [{
                            "args": ["cd /data/tensorflow-mnist-example; pip install -r requirements.txt; python tensorflow_mnist_train_distributed.py"],
                            "command": [
                                "/bin/bash",
                                "-c",
                                "--",
                            ],
                            "image": "tensorflow/tensorflow:latest-gpu",
                            "name": "tensorflow",
                            "resources": {
                                "limits": {
                                    "cpu": "1",
                                    "memory": "3Gi",
                                    "nvidia.com/gpu": "1",
                                },
                            },
                            "volume_mounts": [{
                                "mount_path": "/data",
                                "name": "gcs-fuse-csi-vol",
                                "read_only": False,
                            }],
                        }],
                        "node_selector": {
                            "cloud.google.com/gke-accelerator": "nvidia-tesla-t4",
                        },
                        "restart_policy": "Never",
                        "service_account_name": self.k8s_sa,
                        "tolerations": [{
                            "effect": "NoSchedule",
                            "key": "nvidia.com/gpu",
                            "operator": "Exists",
                        }],
                        "volumes": [{
                            "csi": {
                                "driver": "gcsfuse.csi.storage.gke.io",
                                "read_only": False,
                                "volume_attributes": {
                                    "bucketName": self.bucket,
                                    "mountOptions": "implicit-dirs",
                                },
                            },
                            "name": "gcs-fuse-csi-vol",
                        }],
                    },
                },
            })

            #),opts=pulumi.ResourceOptions(provider=self.provider))
        
    