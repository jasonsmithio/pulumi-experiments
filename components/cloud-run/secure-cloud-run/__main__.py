import pulumi
import pulumi_gcp as gcp
from pulumi_gcp import cloudrunv2 as cloudrun

class cloudRunSecure(pulumi.ComponentResource):
    def __init__(self, name, policy_name='default', opts=None):
        self.name = name