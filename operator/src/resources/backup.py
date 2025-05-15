from typing import Dict, List, Any, Optional, Tuple

from kubernetes import client
from kubernetes.client.rest import ApiException

from ..utils.helpers import get_k8s_batch_api, get_k8s_core_api
from ..utils.config import get_backup_image, get_image_pull_secret


def create_backup_cronjob(
    name: str,
    namespace: str,
    schedule: str,
    mysql_ref: str,
    s3_config: Optional[Dict[str, Any]] = None,
    labels: Optional[Dict[str, str]] = None,
    owner_references: Optional[List[Any]] = None,
    node_selector: Optional[Dict[str, str]] = None,
) -> Tuple[client.V1CronJob, bool]:
    """
    Create a CronJob to backup MySQL instance on a schedule.
    
    Args:
        name: MySQL instance name
        namespace: Kubernetes namespace
        schedule: Cron schedule expression (e.g. "0 2 * * *")
        mysql_ref: Name of the MySQL instance
        s3_config: S3 configuration for backup storage
        labels: Labels to add to the CronJob
        owner_references: K8s owner references
        node_selector: Node selector for the CronJob
    Returns:
        The created/updated CronJob and a boolean indicating if it was newly created
    """
    batch_api = get_k8s_batch_api()
    
    if s3_config is None:
        s3_config = {}
    
   # Prepare environment variables
    env = [
        client.V1EnvVar(
            name="S3_BUCKET",
            value=s3_config.get("bucket")
        ),
        client.V1EnvVar(
            name="S3_ENDPOINT",
            value=s3_config.get("endpoint")
        ),
        client.V1EnvVar(
            name="S3_PREFIX",
            value=s3_config.get("prefix", "default")
        )
    ]
    
    # Add keep days if provided
    if "keepDays" in s3_config:
        env.append(
            client.V1EnvVar(
                name="S3_KEEP_DAYS",
                value=str(s3_config.get("keepDays"))
            )
        )

    # Prepare image pull secrets
    k8s_image_pull_secrets = None
    if get_image_pull_secret():
        k8s_image_pull_secrets = [
            client.V1LocalObjectReference(name=get_image_pull_secret())
        ]
    
    # mount the mysql data dir to /var/lib/mysql
    volumes = [
        client.V1Volume(
            name="mysql-data",
            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=f'{mysql_ref}-data')
        )
    ]

    volume_mounts = [
        client.V1VolumeMount(
            name="mysql-data",
            mount_path="/var/lib/mysql"
        )
    ]
    
    # Create job template
    backup_container = client.V1Container(
        name="mysql-backup",
        image=get_backup_image(),
        image_pull_policy="IfNotPresent",
        env=env,
        env_from=[
            client.V1EnvFromSource(
                secret_ref=client.V1SecretEnvSource(
                    name=f"{mysql_ref}-credentials"
                )
            ),
            client.V1EnvFromSource(
              secret_ref=client.V1SecretEnvSource(
                name=s3_config.get("secretRef")
              )
            )
        ],
        resources=client.V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "128Mi"},
            limits={"cpu": "200m", "memory": "256Mi"}
        ),
        volume_mounts=volume_mounts
    )
    
    # Create the CronJob object
    cronjob_name = f"{name}-backup"
    cronjob_spec = client.V1CronJobSpec(
        schedule=schedule,
        job_template=client.V1JobTemplateSpec(
            metadata=client.V1ObjectMeta(
                name=cronjob_name,
                labels=labels
            ),
            spec=client.V1JobSpec(
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels=labels
                    ),
                    spec=client.V1PodSpec(
                        containers=[backup_container],
                        restart_policy="OnFailure",
                        image_pull_secrets=k8s_image_pull_secrets,
                        node_selector=node_selector,
                        volumes=volumes,
                        
                    )
                ),
                backoff_limit=3
            )
        ),
        concurrency_policy="Forbid",
        successful_jobs_history_limit=3,
        failed_jobs_history_limit=1,
        suspend=False
    )
    
    # Prepare the CronJob metadata
    cronjob_metadata = client.V1ObjectMeta(
        name=cronjob_name,
        namespace=namespace,
        labels=labels
    )
    
    if owner_references:
        processed_owner_refs = []
        for owner_ref in owner_references:
            if isinstance(owner_ref, client.V1OwnerReference):
                processed_owner_refs.append(owner_ref)
            else:
                processed_owner_refs.append(client.V1OwnerReference(**owner_ref))
        cronjob_metadata.owner_references = processed_owner_refs
    
    # Create the final CronJob object
    cronjob = client.V1CronJob(
        api_version="batch/v1",
        kind="CronJob",
        metadata=cronjob_metadata,
        spec=cronjob_spec
    )
    
    # Try to get existing CronJob, create if not found
    created = False
    try:
        batch_api.read_namespaced_cron_job(name=cronjob_name, namespace=namespace)
        # If found, update
        batch_api.replace_namespaced_cron_job(
            name=cronjob_name,
            namespace=namespace,
            body=cronjob
        )
    except ApiException as e:
        if e.status == 404:
            # Not found, create
            batch_api.create_namespaced_cron_job(
                namespace=namespace,
                body=cronjob
            )
            created = True
        else:
            # Re-raise any other exception
            raise
    
    return cronjob, created


def delete_backup_cronjob(name: str, namespace: str) -> None:
    """
    Delete a MySQL backup CronJob.
    
    Args:
        name: MySQL instance name
        namespace: Kubernetes namespace
    """
    batch_api = get_k8s_batch_api()
    cronjob_name = f"{name}-backup"
    
    try:
        batch_api.delete_namespaced_cron_job(
            name=cronjob_name,
            namespace=namespace,
            body=client.V1DeleteOptions(
                propagation_policy="Foreground",
                grace_period_seconds=5
            )
        )
    except ApiException as e:
        if e.status != 404:  # Ignore if already deleted
            raise 