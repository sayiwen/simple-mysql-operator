from typing import Dict, List, Any, Optional

from kubernetes import client
from kubernetes.client.rest import ApiException

from src.utils.config import get_mysql_image, get_restore_image, get_image_pull_secret

from ..utils.helpers import get_k8s_apps_api, format_labels

def create_mysql_deployment(
    name: str,
    namespace: str,
    storage_claim_name: str,
    secret_name: str,
    db_name: str,
    labels: Dict[str, str],
    resources: Optional[Dict[str, Any]] = None,
    node_selector: Optional[Dict[str, str]] = None,
    affinity: Optional[Dict[str, Any]] = None,
    tolerations: Optional[List[Dict[str, Any]]] = None,
    owner_references: Optional[List[Dict[str, Any]]] = None,
    restore_from_backup: Optional[Dict[str, Any]] = None
) -> client.V1Deployment:
    """Create a MySQL deployment."""
    apps_api = get_k8s_apps_api()
    
    # Prepare volume mounts
    volume_mounts = [
        client.V1VolumeMount(
            name="data",
            mount_path="/var/lib/mysql"
        ),
        #env
        client.V1VolumeMount(
            name="env",
            mount_path="/env"
        )
    ]
    
    # Prepare volumes
    volumes = [
        client.V1Volume(
            name="data",
            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                claim_name=storage_claim_name
            )
        ),
        #env
        client.V1Volume(
            name="env",
            secret=client.V1SecretVolumeSource(
                secret_name=secret_name
            )
        )
    ]
    
    # Env variables
    env = [
        client.V1EnvVar(
            name="MYSQL_DATABASE",
            value=db_name
        ),
        client.V1EnvVar(
            name="MYSQL_ROOT_PASSWORD_FILE",
            value="/env/MYSQL_PASSWORD"
        )
    ]
    
    # Prepare container
    container = client.V1Container(
        name="mysql",
        image=get_mysql_image(),
        image_pull_policy="IfNotPresent",
        ports=[client.V1ContainerPort(container_port=3306)],
        volume_mounts=volume_mounts,
        env=env,
        resources=client.V1ResourceRequirements(
            requests=resources.get("requests", {}),
            limits=resources.get("limits", {})
        ) if resources else None
    )
    
    # Handle init container for restore if needed
    init_containers = []
    if restore_from_backup:
        s3_config = restore_from_backup.get("s3", {})
        s3_secret_ref = s3_config.get("secretRef")
        backup_id = restore_from_backup.get("backupId", "")
        
        # Add volume for S3 credentials
        if s3_secret_ref:
            
            # Create restore init container
            restore_container = client.V1Container(
                name="restore",
                image=get_restore_image(),
                image_pull_policy="IfNotPresent",
                volume_mounts=[
                    client.V1VolumeMount(
                        name="data",
                        mount_path="/app/restore"
                    )
                ],
                env=[
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
                ],
                env_from=[
                    client.V1EnvFromSource(
                        secret_ref=client.V1SecretEnvSource(
                            name=s3_secret_ref
                        )
                    )
                ]
            )
            
            # Add backup ID if specified
            if backup_id:
                restore_container.env.append(
                    client.V1EnvVar(
                        name="BACKUP_ID",
                        value=backup_id
                    )
                )
                
            init_containers.append(restore_container)
    
    # Create deployment spec
    spec = client.V1DeploymentSpec(
        replicas=1,
        selector=client.V1LabelSelector(
            match_labels=labels
        ),
        template=client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels=labels
            ),
            spec=client.V1PodSpec(
                containers=[container],
                init_containers=init_containers if init_containers else None,
                volumes=volumes,
                node_selector=node_selector,
                affinity=affinity,
                tolerations=tolerations,
                image_pull_secrets=[
                    client.V1LocalObjectReference(name=get_image_pull_secret())
                ] if get_image_pull_secret() else None
            )
        ),
        strategy=client.V1DeploymentStrategy(
            type="Recreate"  # Ensure we don't have multiple instances running
        )
    )
    
    # Create the deployment
    deployment = client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels=labels,
            owner_references=owner_references
        ),
        spec=spec
    )
    
    try:
        # Check if deployment already exists
        existing_deployment = apps_api.read_namespaced_deployment(name, namespace)
        # Update if it exists
        apps_api.replace_namespaced_deployment(name, namespace, deployment)
    except ApiException as e:
        if e.status == 404:
            # Create if it doesn't exist
            apps_api.create_namespaced_deployment(namespace, deployment)
        else:
            raise
    
    return deployment 