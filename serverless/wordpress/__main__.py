import pulumi
import pulumi_gcp
from pulumi import Output, Config
from pulumi_gcp.cloudrun import (
    ServiceTemplateMetadataArgs,
    ServiceTemplateSpecContainerEnvArgs,
)

config = Config()

cloud_sql_instance = pulumi_gcp.sql.DatabaseInstance(
    "wordpress_db",
    database_version="MYSQL_5_7",
    deletion_protection=False,
    settings=pulumi_gcp.sql.DatabaseInstanceSettingsArgs(tier="db-f1-micro"),
)

database = pulumi_gcp.sql.Database(
    "database", instance=cloud_sql_instance.name, name=config.require("db-name")
)

users = pulumi_gcp.sql.User(
    "wordpress",
    name=config.require("db-name"),
    instance=cloud_sql_instance.name,
    password=config.require_secret("db-password"),
)

sql_instance_url = Output.concat(
    "mysql://",
    config.require("db-name"),
    ":",
    config.require_secret("db-password"),
    "@/",
    config.require("db-name"),
    "?host=/cloudsql/",
    cloud_sql_instance.connection_name,
)

env_vars = [
ServiceTemplateSpecContainerEnvArgs(name="WORDPRESS_DB_HOST", value=cloud_sql_instance.name),
ServiceTemplateSpecContainerEnvArgs(name="WORDPRESS_DB_USER", value="wordpress"),
ServiceTemplateSpecContainerEnvArgs(name="WORDPRESS_DB_PASSWORD", value=config.require_secret("db-password")),
ServiceTemplateSpecContainerEnvArgs(name="WORDPRESS_DB_NAME", value=cloud_sql_instance.connection_name),
ServiceTemplateSpecContainerEnvArgs(name="WORDPRESS_TABLE_PREFIX",value="wp"),
]

cloud_run = pulumi_gcp.cloudrun.Service(
    "wordpress",
    location=Config("gcp").require("region"),
    template=pulumi_gcp.cloudrun.ServiceTemplateArgs(
        metadata=ServiceTemplateMetadataArgs(
            annotations={
                "run.googleapis.com/cloudsql-instances": cloud_sql_instance.connection_name
            }
        ),
        spec=pulumi_gcp.cloudrun.ServiceTemplateSpecArgs(
            containers=[
                pulumi_gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                    image="wordpress",
                    envs=env_vars,
                )
            ],
        ),
    ),
    traffics=[
        pulumi_gcp.cloudrun.ServiceTrafficArgs(
            latest_revision=True,
            percent=100,
        )
    ],
)

pulumi.export("cloud_sql_instance_name", cloud_sql_instance.name)
pulumi.export("cloud_run_url", cloud_run.statuses[0].url)