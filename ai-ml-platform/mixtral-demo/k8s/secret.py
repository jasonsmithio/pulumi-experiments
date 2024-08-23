import pulumi
import pulumi_kubernetes as k8s

# Define the Secret
my_secret = k8s.core.v1.Secret(
    "my-secret",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="my-secret"
    ),
    data={
        "username": "dXNlcm5hbWU=",  # base64 encoded 'username'
        "password": "cGFzc3dvcmQ="   # base64 encoded 'password'
    },
    type="Opaque"
)

# Export the name of the created secret
pulumi.export("secret_name", my_secret.metadata["name"])