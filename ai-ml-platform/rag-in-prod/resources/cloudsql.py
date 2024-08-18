import pulumi
import pulumi_gcp as gcp
import pulumi_random as random


class CloudSQL:

    def __init__(self, dbinstance, dbname, region, tier, network, version='POSTGRES_15'):
        self.dbinstance = dbinstance
        self.dbname = dbname
        self.region = region
        self.tier = tier
        self.network = network
        self.version = version


    def pgbuild(self):

        pginstance = gcp.sql.DatabaseInstance(self.dbinstance,
            region=self.region,
            database_version=self.version,
            settings=gcp.sql.DatabaseInstanceSettingsArgs(
                tier=self.tier,
                ip_configuration=gcp.sql.DatabaseInstanceSettingsIpConfigurationArgs(
                    ipv4_enabled=True,
                    private_network = self.network,
                    enable_private_path_for_google_cloud_services=True,
                ),
            ),
            deletion_protection=False)
           
        pgsql = gcp.sql.Database(self.dbname,
            name=self.dbname,
            instance=self.dbinstance,
            deletion_policy="ABANDON",
            opts=pulumi.ResourceOptions(depends_on=[pginstance])
            )
        
        user = gcp.sql.User("users",
            name=self.dbname,
            instance= self.dbinstance,
            password= random.RandomPassword("password",
                length=16,
                special=True,
                override_special="!#$%&*()-_=+[]{}<>:?"),
            opts=pulumi.ResourceOptions(depends_on=[pgsql])                
            )

        #return user

