from typing import Dict, List, Any, Optional
import datetime
import base64
from kubernetes import client
from kubernetes.client.rest import ApiException

from ..utils.helpers import get_k8s_batch_api, format_labels, get_k8s_core_api

from src.utils.config import get_backup_image, get_image_pull_secret

def create_backup_job(
    name: str,
    namespace: str,
    mysql_ref: str,
    s3_config: Dict[str, Any],
    labels: Dict[str, str],
    node_selector: Optional[Dict[str, str]] = None,
    owner_references: Optional[List[Any]] = None,
    ttl_seconds_after_finished: int = 30
) -> client.V1Job:
    """Create a MySQL backup job.
    
    Args:
        name: Name of the backup
        namespace: Namespace to create the job in
        mysql_ref: Name of the MySQL instance to backup
        s3_config: S3 configuration for the backup
        labels: Labels to apply to the job
        node_selector: Node selector for the backup pod (should match MySQL's node selector)
        owner_references: Owner references for the job
        ttl_seconds_after_finished: Time in seconds after which the job will be deleted (default: 1 day)
        
    Returns:
        The created job
    """
    batch_api = get_k8s_batch_api()
    
    # Generate a unique backup ID with timestamp
    backup_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    job_name = f"{name}-{backup_id}"


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
    
    # Create the job
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name=job_name,
            namespace=namespace,
            labels=labels,
            owner_references=owner_references
        ),
        spec=client.V1JobSpec(
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels=labels
                ),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name="backup",
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
                            volume_mounts=volume_mounts
                        )
                    ],
                    volumes=volumes,
                    restart_policy="Never",
                    node_selector=node_selector,
                    image_pull_secrets=k8s_image_pull_secrets
                )
            ),
            backoff_limit=3,
            ttl_seconds_after_finished=ttl_seconds_after_finished
        )
    )
    
    # Create the job
    batch_api.create_namespaced_job(namespace, job)
    
    return job 