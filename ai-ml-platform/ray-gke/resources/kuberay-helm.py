import pulumi
import pulumi_kubernetes as kubernetes

class Kuberay:

    def __init__(self, provider):
        self.provider = provider

    def mixtral8x7b(self):
        self.provider = "a"