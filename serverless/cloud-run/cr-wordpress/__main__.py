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
cr_max_instances=config.get("cr-max", 5)
db_tier=config.get("db-tier", "db-f1-micro")
use_gclb=config.get_bool("use_gclb", True)

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
    secret_data=secrets.token_urlsafe(15)
    )  

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

# Setup GCLB If User requested it

if use_gclb is True:

    # Create a Global IP Address
    wp_ip_address = pulumi_gcp.compute.GlobalAddress("wp_ip_address", 
        name="wp-ip-address",
        address_type="EXTERNAL",
        ip_version="IPV4",
        description="Global IP Address for Wordpress on Cloud Run",
    )

    # Create a Serverles NEG
    wp_cr_neg = pulumi_gcp.compute.RegionNetworkEndpointGroup("wp_cr_neg",
        name="wp-cr-neg",
        region=gcp_region,
        network_endpoint_type="SERVERLESS",
        cloud_run=pulumi_gcp.compute.RegionNetworkEndpointGroupCloudRunArgs(
            service=wordpress_cr_service.name,
        ),
    )

    #Create a Backend Service
    wp_backend_service = pulumi_gcp.compute.BackendService("wp-backend-service",
        name="wp-backend-service",
        enable_cdn=True,
        protocol="HTTPS",
        backends=[pulumi_gcp.compute.BackendServiceBackendArgs(
            group=wp_cr_neg.id,
        )],
    )   
    
    # Create URL Paths 
    cr_url_paths = pulumi_gcp.compute.URLMap("cr-url-paths",
        name="cr-url-paths",
        default_service=wp_backend_service.id,
    )  

    # Create SSL Certificate
    wp_cr_cert = pulumi_gcp.compute.ManagedSslCertificate("wp_cr_certificate",
        name="wp-cr-certificate",
        managed=pulumi_gcp.compute.ManagedSslCertificateManagedArgs(
            domains=[wp_ip_address.address.apply(lambda address: f"wordpress-{address.replace(".","-")}.nip.io")]
            ),
        opts=pulumi.ResourceOptions(depends_on=[wp_ip_address]),
    ) 
    
    # Create HTTP and HTTPS proxies
    cr_http_proxy = pulumi_gcp.compute.TargetHttpProxy("cr-http-proxy",
        name="cr-http-proxy",
        url_map=cr_url_paths.id,
    )

    cr_https_proxy = pulumi_gcp.compute.TargetHttpsProxy("cr-https-proxy",
        name="cr-https-proxy",
        url_map=cr_url_paths.id,
        ssl_certificates=[wp_cr_cert.id],
    )

    # Create HTTP and HTTPS Global Forwarding Rules
    wp_http_forwarding_rule = pulumi_gcp.compute.GlobalForwardingRule("wp-http-forwarding-rule",
        name="wp-http-forwarding-rule",
        target=cr_http_proxy.self_link,
        port_range="80",
        ip_protocol="TCP",
        ip_address=wp_ip_address.address,
        opts=pulumi.ResourceOptions(depends_on=[wp_ip_address]),
    )

    wp_https_forwarding_rule = pulumi_gcp.compute.GlobalForwardingRule("wp-https-forwarding-rule",
        name="wp-https-forwarding-rule",
        ip_address=wp_ip_address.address,
        target=cr_https_proxy.self_link,
        port_range="443",
        load_balancing_scheme="EXTERNAL",        
        opts=pulumi.ResourceOptions(depends_on=[wp_ip_address]),
    )

    # Exporting Full nip.io URL
    pulumi.export("WordPress URL", wp_ip_address.address.apply(lambda address: f"wordpress-{address.replace(".","-")}.nip.io"))

elif use_gclb is False:
    pass
else:
    pulumi.export("Load Balancer Message", "use_gclb was not set properly, defaulting to False")
    pass


#Export Values
pulumi.export("cloud_sql_instance_name", cloud_sql_instance.name)
pulumi.export("cloud_run_url", wordpress_cr_service.uri)