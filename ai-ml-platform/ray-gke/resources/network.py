import pulumi
from pulumi import Input
from typing import Optional, Dict, TypedDict, Any
import pulumi_gcp as gcp

class NetworkArgs(TypedDict, total=False):
    projectId: Input[str]
    networkName: Input[str]
    routingMode: Input[str]
    subnet01Ip: Input[str]
    subnet01Name: Input[str]
    subnet01Region: Input[str]
    subnet02Ip: Input[str]
    subnet02Name: Input[str]
    subnet02Region: Input[str]

class Network(pulumi.ComponentResource):
    def __init__(self, name: str, args: NetworkArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:Network", name, args, opts)

        # Copyright 2024 Google LLC
        #
        # Licensed under the Apache License, Version 2.0 (the "License");
        # you may not use this file except in compliance with the License.
        # You may obtain a copy of the License at
        #
        #      http://www.apache.org/licenses/LICENSE-2.0
        #
        # Unless required by applicable law or agreed to in writing, software
        # distributed under the License is distributed on an "AS IS" BASIS,
        # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
        # See the License for the specific language governing permissions and
        # limitations under the License.
        vpc_network = gcp.compute.Network(f"{name}-vpc-network",
            auto_create_subnetworks=False,
            name=args["networkName"],
            project=args["projectId"],
            routing_mode=args["routingMode"],
            opts=pulumi.ResourceOptions(parent=self))

        subnet_1 = gcp.compute.Subnetwork(f"{name}-subnet-1",
            ip_cidr_range=args["subnet01Ip"],
            name=args["subnet01Name"],
            network=vpc_network.id,
            private_ip_google_access=True,
            project=args["projectId"],
            region=args["subnet01Region"],
            opts=pulumi.ResourceOptions(parent=self))

        subnet_2 = gcp.compute.Subnetwork(f"{name}-subnet-2",
            ip_cidr_range=args["subnet02Ip"],
            name=args["subnet02Name"],
            network=vpc_network.id,
            private_ip_google_access=True,
            project=args["projectId"],
            region=args["subnet02Region"],
            opts=pulumi.ResourceOptions(parent=self))

        self.subnet-1 = subnet_1.id
        self.subnet-2 = subnet_2.id
        self.vpc = vpc_network.id
        self.register_outputs({
            'subnet-1': subnet_1.id, 
            'subnet-2': subnet_2.id, 
            'vpc': vpc_network.id
        })