import pulumi
from pulumi import Input
from typing import Optional, Dict, TypedDict, Any
import pulumi_gcp as gcp
import pulumi_std as std


def not_implemented(msg):
    raise NotImplementedError(msg)

class VmReservationsArgs(TypedDict, total=False):
    accelerator: Input[str]
    acceleratorCount: Input[float]
    clusterName: Input[str]
    machineReservationCount: Input[float]
    machineType: Input[str]
    projectId: Input[str]
    zone: Input[str]

class VmReservations(pulumi.ComponentResource):
    def __init__(self, name: str, args: VmReservationsArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:VmReservations", name, args, opts)

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
        machine_reservation = gcp.compute.Reservation(f"{name}-machine_reservation",
            name=not_implemented("format(\"%s-%s\",var.cluster_name,\"reservation\")"),
            project=args["projectId"],
            specific_reservation_required=True,
            zone=args["zone"],
            specific_reservation=gcp.compute.ReservationSpecificReservationArgs(
                count=args["machineReservationCount"],
                instance_properties=gcp.compute.ReservationSpecificReservationInstancePropertiesArgs(
                    machine_type=args["machineType"],
                    guest_accelerators=[gcp.compute.ReservationSpecificReservationInstancePropertiesGuestAcceleratorArgs(
                        accelerator_count=args["acceleratorCount"],
                        accelerator_type=args["accelerator"],
                    )],
                ),
            ),
            opts=pulumi.ResourceOptions(parent=self))

        self.reservationName = std.split_output(separator=/,
            text=machine_reservation.id).result[5]
        self.register_outputs({
            'reservationName': std.split_output(separator=/,
                text=machine_reservation.id).result[5]
        })