import pulumi
import pulumi_gcp
from pulumi import Output, Config
from pulumi_gcp.cloudrunv2 import (
    ServiceIamBinding,
)

config = pulumi.Config()

gcp_project = Config("gcp").require("project")
gcp_region = Config("gcp").get("region")

# LLM Bucket
wordpress_bucket = pulumi_gcp.storage.Bucket("wordpress-bucket",
    name=str(gcp_project)+"-wordpress-bucket",
    location=gcp_region,
    force_destroy=True,
    uniform_bucket_level_access=True,
    )

cloud_sql_instance = pulumi_gcp.sql.DatabaseInstance("wordpress-db",
    name="wordpress-db",
    database_version="MYSQL_8_0",
    deletion_protection=False,
    settings=pulumi_gcp.sql.DatabaseInstanceSettingsArgs(tier="db-f1-micro"),
)

database = pulumi_gcp.sql.Database(
    "database", instance=cloud_sql_instance.name, name=config.require("db-name")
)

users = pulumi_gcp.sql.User("wp-user",
    name="wp-user",
    host="%",
    instance=cloud_sql_instance.name,
    password=config.require_secret("db-password"),
)

# Create Service Account
wp_service_account = pulumi_gcp.serviceaccount.Account("my-service-account",
    account_id="wp-service-account",
    display_name="Wordpress Service Account",
    description="This is a service account created using Pulumi for our Wordpress installation on Cloud Run",
)

# Output variable for service account binding
service_account_member = Output.concat(
    "serviceAccount:",
    wp_service_account.email,
)

# Bind the new Service Account to 3 roles
storage_iam_binding = pulumi_gcp.projects.IAMMember("storage-wp-service-account-binding",
    project=gcp_project,
    role="roles/storage.admin",
    member=service_account_member,
    opts=pulumi.ResourceOptions(depends_on=[wp_service_account]),
)

cloudsql_iam_binding = pulumi_gcp.projects.IAMMember("cloudsql-wp-service-account-binding",
    project=gcp_project,
    role="roles/cloudsql.client",
    member=service_account_member,
    opts=pulumi.ResourceOptions(depends_on=[wp_service_account]),
)

cr_iam_binding = pulumi_gcp.projects.IAMMember("cr-wp-service-account-binding",
    project=gcp_project,
    role="roles/run.invoker", 
    member=service_account_member,
    opts=pulumi.ResourceOptions(depends_on=[wp_service_account]),
)


sql_instance_url = Output.concat(
    ":/cloudsql/",
    cloud_sql_instance.connection_name,
)

# Create a Cloud Run Service
wordpress_cr_service = pulumi_gcp.cloudrunv2.Service("wordpress",
    name="wordpress",
    location=gcp_region,
    ingress="INGRESS_TRAFFIC_ALL",
    deletion_protection=False,
    template={
        "service_account": wp_service_account.email,
        "scaling": {
            "max_instance_count": 2,
        },
        "volumes": [{
            "name": "cloudsql",
            "cloud_sql_instance": {
                "instances": [cloud_sql_instance.connection_name],
            },
        },{
            "name": "wordpress-bucket",
            "gcs": {
                    "bucket": wordpress_bucket.name,
                    "read_only": False,
                    },
        }],
        "containers": [{
            "ports": {
                "container_port": 80,
            },
            "image": "wordpress",
            "envs": [
                {
                    "name": "WORDPRESS_DB_HOST",
                    "value": sql_instance_url,
                },
                {
                    "name": "WORDPRESS_DB_USER",
                    "value": users.name,
                },
                {
                    "name": "WORDPRESS_DB_PASSWORD",
                    "value": config.require_secret("db-password"),
                },
                {
                    "name": "WORDPRESS_DB_NAME",
                    "value": cloud_sql_instance.name,
                },
                {
                    "name": "WORDPRESS_TABLE_PREFIX",
                    "value": "wp",
                },
            ],
            "volume_mounts": [{
                "name": "cloudsql",
                "mount_path": "/cloudsql",
                }, {
                "name": "wordpress-bucket",
                "mount_path": "/var/www/html/wp-content/uploads",
            }],
        }],
    },
    traffics=[{
        "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST",
        "percent": 100,
    }],
    opts = pulumi.ResourceOptions(depends_on=[cr_iam_binding]),
)


wordpress_binding = ServiceIamBinding("wordpress-binding",
    project=gcp_project,
    location=gcp_region,
    name=wordpress_cr_service,
    role="roles/run.invoker",
    members=["allUsers"],
    opts=pulumi.ResourceOptions(depends_on=[wordpress_cr_service]),
)

pulumi.export("cloud_sql_instance_name", cloud_sql_instance.name)
pulumi.export("cloud_run_url", wordpress_cr_service.uri)