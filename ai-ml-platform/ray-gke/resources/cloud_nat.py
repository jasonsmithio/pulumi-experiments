import pulumi
from pulumi import Input
from typing import Optional, Dict, TypedDict, Any
import pulumi_gcp as gcp
import pulumi_random as random


def not_implemented(msg):
    raise NotImplementedError(msg)

def single_or_none(elements):
    if len(elements) != 1:
        raise Exception("single_or_none expected input list to have a single element")
    return elements[0]


class Subnetworks(TypedDict, total=False):
    name: Input[str]
    secondaryIpRangeNames: Input[list[str]]
    sourceIpRangesToNat: Input[list[str]]

class CloudNatArgs(TypedDict, total=False):
    createRouter: Input[bool]
    enableDynamicPortAllocation: Input[bool]
    enableEndpointIndependentMapping: Input[bool]
    icmpIdleTimeoutSec: Input[str]
    logConfigEnable: Input[bool]
    logConfigFilter: Input[str]
    maxPortsPerVm: Input[str]
    minPortsPerVm: Input[str]
    name: Input[str]
    natIps: Input[list[str]]
    network: Input[str]
    projectId: Input[str]
    region: Input[str]
    router: Input[str]
    routerAsn: Input[str]
    routerKeepaliveInterval: Input[str]
    sourceSubnetworkIpRangesToNat: Input[str]
    subnetworks: Input[list(Subnetworks)]
    tcpEstablishedIdleTimeoutSec: Input[str]
    tcpTimeWaitTimeoutSec: Input[str]
    tcpTransitoryIdleTimeoutSec: Input[str]
    udpIdleTimeoutSec: Input[str]

class CloudNat(pulumi.ComponentResource):
    def __init__(self, name: str, args: CloudNatArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:CloudNat", name, args, opts)

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
        name_suffix = random.RandomString(f"{name}-name_suffix",
            length=6,
            special=False,
            upper=False,
            opts=pulumi.ResourceOptions(parent=self))

        default_name = name_suffix.result.apply(lambda result: f"cloud-nat-{result}")

        my_name = args["name"] if args["name"] != "" else default_name

        nat_ip_allocate_option = "MANUAL_ONLY" if len(args["natIps"]) > 0 else "AUTO_ONLY"

        router_router = []
        for range in [{"value": i} for i in range(0, 1 if args["createRouter"] else 0)]:
            router_router.append(gcp.compute.Router(f"{name}-router-{range['value']}",
                name=args["router"],
                network=args["network"],
                project=args["projectId"],
                region=args["region"],
                bgp=gcp.compute.RouterBgpArgs(
                    asn=args["routerAsn"],
                    keepalive_interval=args["routerKeepaliveInterval"],
                ),
                opts=pulumi.ResourceOptions(parent=self)))

        my_router = router_router[0].name if args["createRouter"] else args["router"]

        main = gcp.compute.RouterNat(f"{name}-main",
            log_config=single_or_none([{
                "enable": entry["value"]["enable"],
                "filter": entry["value"]["filter"],
            } for entry in [{"key": k, "value": v} for k, v in [{
                "enable": args["logConfigEnable"],
                "filter": args["logConfigFilter"],
            }] if args["logConfigEnable"] == True else []]]),
            subnetworks=[gcp.compute.RouterNatSubnetworkArgs(
                name=entry["value"]["name"],
                source_ip_ranges_to_nats=entry["value"]["sourceIpRangesToNat"],
                secondary_ip_range_names=entry["value"]["secondaryIpRangeNames"] if not_implemented("contains(subnetwork.value.source_ip_ranges_to_nat,\"LIST_OF_SECONDARY_IP_RANGES\")") else [],
            ) for entry in [{"key": k, "value": v} for k, v in args["subnetworks"]]],
            enable_dynamic_port_allocation=args["enableDynamicPortAllocation"],
            enable_endpoint_independent_mapping=args["enableEndpointIndependentMapping"],
            icmp_idle_timeout_sec=args["icmpIdleTimeoutSec"],
            max_ports_per_vm=args["maxPortsPerVm"] if args["enableDynamicPortAllocation"] else None,
            min_ports_per_vm=args["minPortsPerVm"],
            name=my_name,
            nat_ip_allocate_option=nat_ip_allocate_option,
            nat_ips=args["natIps"],
            project=args["projectId"],
            region=args["region"],
            router=my_router,
            source_subnetwork_ip_ranges_to_nat=args["sourceSubnetworkIpRangesToNat"],
            tcp_established_idle_timeout_sec=args["tcpEstablishedIdleTimeoutSec"],
            tcp_time_wait_timeout_sec=args["tcpTimeWaitTimeoutSec"],
            tcp_transitory_idle_timeout_sec=args["tcpTransitoryIdleTimeoutSec"],
            udp_idle_timeout_sec=args["udpIdleTimeoutSec"],
            opts=pulumi.ResourceOptions(parent=self))

        self.name = my_name
        self.natIpAllocateOption = nat_ip_allocate_option
        self.region = main.region
        self.routerName = my_router
        self.register_outputs({
            'name': my_name, 
            'natIpAllocateOption': nat_ip_allocate_option, 
            'region': main.region, 
            'routerName': my_router
        })