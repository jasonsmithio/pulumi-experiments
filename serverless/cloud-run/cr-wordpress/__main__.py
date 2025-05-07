import pulumi
import pulumi_gcp
import secrets
from pulumi import Output, Config
from pulumi_gcp.cloudrunv2 import (
    ServiceIamBinding,
)

config = pulumi.Config()

gcp_project = Config("gcp").require("project")
gcp_region = Config("gcp").get("region")
cr_max_instances=config.get("cr-max", 2)
db_tier=config.get("db-tier", "db-f1-micro")

# LLM Bucket
wordpress_bucket = pulumi_gcp.storage.Bucket("wordpress-bucket",
    name=str(gcp_project)+"-wordpress-bucket",
    location=gcp_region,
    force_destroy=True,
    uniform_bucket_level_access=True,
    )

# Create DB Password
wp_db_secret = pulumi_gcp.secretmanager.Secret("wp-mysql-secret",
    secret_id="wp-mysql-secret",
    replication={
        "user_managed": {
            "replicas": [
                {
                    "location": gcp_region,
                },
                {
                    "location": "us-east1",
                },
            ],
        },
    })

# Add a secret version with the secret payload
wp_db_secret_version = pulumi_gcp.secretmanager.SecretVersion("my-secret-version",
    secret=wp_db_secret.id,
    secret_data=secrets.token_urlsafe(15))  

# Setup Cloud SQL with MySQL isntance, database, and user
cloud_sql_instance = pulumi_gcp.sql.DatabaseInstance("wordpress-db",
    name="wordpress-db",
    database_version="MYSQL_8_0",
    deletion_protection=False,
    settings=pulumi_gcp.sql.DatabaseInstanceSettingsArgs(tier=db_tier),
)

database = pulumi_gcp.sql.Database(
    "database", instance=cloud_sql_instance.name, name=config.require("db-name")
)

users = pulumi_gcp.sql.User("wp-user",
    name="wp-user",
    host="%",
    instance=cloud_sql_instance.name,
    password=wp_db_secret_version.version,
)

# Create Service Account for Cloud Run
wp_service_account = pulumi_gcp.serviceaccount.Account("my-service-account",
    account_id="wp-service-account",
    display_name="Wordpress Service Account",
    description="This is a service account created using Pulumi for our Wordpress installation on Cloud Run",
)

# Bind the new Service Account to 3 roles
storage_iam_binding = pulumi_gcp.projects.IAMMember("storage-wp-service-account-binding",
    project=gcp_project,
    role="roles/storage.admin",
    member=wp_service_account.email.apply(lambda email: f"serviceAccount:{email}"),
    opts=pulumi.ResourceOptions(depends_on=[wp_service_account]),
)

cloudsql_iam_binding = pulumi_gcp.projects.IAMMember("cloudsql-wp-service-account-binding",
    project=gcp_project,
    role="roles/cloudsql.client",
    member=wp_service_account.email.apply(lambda email: f"serviceAccount:{email}"),
    opts=pulumi.ResourceOptions(depends_on=[wp_service_account]),
)

cr_iam_binding = pulumi_gcp.projects.IAMMember("cr-wp-service-account-binding",
    project=gcp_project,
    role="roles/run.invoker", 
    member=wp_service_account.email.apply(lambda email: f"serviceAccount:{email}"),
    opts=pulumi.ResourceOptions(depends_on=[wp_service_account]),
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
            "max_instance_count": cr_max_instances,
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
                    "value": cloud_sql_instance.connection_name.apply(lambda connection_name: f":/cloudsql/{connection_name}"),
                    #"value": sql_instance_url,
                },
                {
                    "name": "WORDPRESS_DB_USER",
                    "value": users.name,
                },
                {
                    "name": "WORDPRESS_DB_PASSWORD",
                    "value": wp_db_secret_version.version,
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