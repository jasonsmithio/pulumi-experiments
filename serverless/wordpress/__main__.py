import pulumi
import pulumi_gcp
from pulumi import Output, Config
from pulumi_gcp.cloudrunv2 import (
    ServiceTemplateMetadataArgs,
    ServiceTemplateSpecContainerEnvArgs,
    ServiceIamBinding,
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

wordpress_cr_service = pulumi_gcp.cloudrun.Service(
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
                    envs=[
                        {"name":"WORDPRESS_DB_HOST", "value":"cloud_sql_instance.connection_name"},
                        {"name":"WORDPRESS_DB_USER" , "value":config.require("db-name")},
                        {"name":"WORDPRESS_DB_PASSWORD", "value":config.require_secret("db-password")},
                        {"name":"WORDPRESS_DB_NAME" , "value":cloud_sql_instance.name},
                        {"name":"WORDPRESS_TABLE_PREFIX" , "value":"wp"},
                    ],
                    ports=[
                    pulumi_gcp.cloudrun.ServiceTemplateSpecContainerPortArgs(
                        container_port=80,
                        ),
                    ],
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

wordpress_binding = ServiceIamBinding("openwebui-binding",
    project=config.require("project")
    location=config.get("region")
    name=wordpress_cr_service,
    role="roles/run.invoker",
    members=["allUsers"],
    opts=pulumi.ResourceOptions(depends_on=[wordpress_cr_service]),
)

pulumi.export("cloud_sql_instance_name", cloud_sql_instance.name)
pulumi.export("cloud_run_url", wordpress_cr_service.statuses[0].url)