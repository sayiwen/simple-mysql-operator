from typing import Dict, Any, List, Optional
from kubernetes import client
from kubernetes.client.rest import ApiException

from src.utils.config import get_phpmyadmin_image, get_image_pull_secret

def create_phpmyadmin_deployment(
    name: str,
    namespace: str,
    mysql_service_name: str,
    port: int = 8080,
    labels: Dict[str, str] = None,
    resources: Dict[str, Any] = None,
    node_selector: Dict[str, str] = None,
    owner_references: List[Any] = None
):
    """
    Create or update a phpMyAdmin deployment for a MySQL instance.
    
    Args:
        name: Name of the MySQL instance
        namespace: Namespace to deploy to
        mysql_service_name: Name of the MySQL service to connect to
        port: Port to expose phpMyAdmin on
        labels: Labels to apply to the deployment
        resources: Resource requests and limits
        node_selector: Node selector for the deployment
        owner_references: List of owner references
    
    Returns:
        The created/updated Deployment
    """
    
    if resources is None:
        resources = {
            "requests": {
                "memory": "128Mi",
                "cpu": "100m"
            },
            "limits": {
                "memory": "256Mi",
                "cpu": "200m"
            }
        }
    
    phpmyadmin_name = f"{name}-phpmyadmin"
    
    # Create specific labels for phpMyAdmin resources
    phpmyadmin_labels = {
        "app": phpmyadmin_name,
        "instance": name,
        "component": "phpmyadmin",
        "managed-by": "mysql-operator"
    }
    
    # Create container
    container = client.V1Container(
        name="phpmyadmin",
        image=get_phpmyadmin_image(),
        ports=[client.V1ContainerPort(container_port=80)],
        env=[
            client.V1EnvVar(name="PMA_HOST", value=mysql_service_name),
            client.V1EnvVar(name="PMA_PORT", value="3306"),
            client.V1EnvVar(name="MEMORY_LIMIT", value="1024M"),
            client.V1EnvVar(name="UPLOAD_LIMIT", value="2048M"),
            client.V1EnvVar(name="PHP_UPLOAD_MAX_FILESIZE", value="2000M"),
            client.V1EnvVar(name="PHP_POST_MAX_SIZE", value="2000M")
        ],
        resources=client.V1ResourceRequirements(
            requests=resources.get("requests", {}),
            limits=resources.get("limits", {})
        ),
    )
    
    # Create deployment
    deployment_spec = client.V1DeploymentSpec(
        replicas=1,
        selector=client.V1LabelSelector(
            match_labels={"app": phpmyadmin_name}
        ),
        template=client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels=phpmyadmin_labels
            ),
            spec=client.V1PodSpec(
                containers=[container],
                node_selector=node_selector,
                image_pull_secrets=[
                    client.V1LocalObjectReference(name=get_image_pull_secret())
                ] if get_image_pull_secret() else None
            ),
            
        )
    )
    
    # Create deployment object
    deployment = client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=client.V1ObjectMeta(
            name=phpmyadmin_name,
            namespace=namespace,
            labels=phpmyadmin_labels,
            owner_references=owner_references
        ),
        spec=deployment_spec
    )
    
    # Create or update the deployment
    api_instance = client.AppsV1Api()
    
    try:
        # Try to get the deployment
        api_instance.read_namespaced_deployment(phpmyadmin_name, namespace)
        # If it exists, update it
        api_instance.patch_namespaced_deployment(
            name=phpmyadmin_name,
            namespace=namespace,
            body=deployment
        )
        
        return deployment, False
    except ApiException as e:
        if e.status == 404:
            # If it doesn't exist, create it
            api_instance.create_namespaced_deployment(
                namespace=namespace,
                body=deployment
            )
            
            return deployment, True
        else:
            # If there's another error, raise it
            raise e

def create_phpmyadmin_service(
    name: str,
    namespace: str,
    port: int = 8080,
    labels: Dict[str, str] = None,
    owner_references: List[Any] = None
):
    """
    Create or update a phpMyAdmin service for a MySQL instance.
    
    Args:
        name: Name of the MySQL instance
        namespace: Namespace to deploy to
        port: Port to expose phpMyAdmin on
        labels: Labels to apply to the service
        owner_references: List of owner references
    
    Returns:
        The created/updated Service
    """
    
    phpmyadmin_name = f"{name}-phpmyadmin"
    
    # Create specific labels for phpMyAdmin resources
    phpmyadmin_labels = {
        "app": phpmyadmin_name,
        "instance": name,
        "component": "phpmyadmin",
        "managed-by": "mysql-operator"
    }
    
    # Create service object
    service = client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=client.V1ObjectMeta(
            name=phpmyadmin_name,
            namespace=namespace,
            labels=phpmyadmin_labels,
            owner_references=owner_references
        ),
        spec=client.V1ServiceSpec(
            selector={"app": phpmyadmin_name},
            ports=[
                client.V1ServicePort(
                    port=port,
                    target_port=80,
                    protocol="TCP",
                    name="http"
                )
            ],
            type="NodePort"
        )
    )
    
    # Create or update the service
    api_instance = client.CoreV1Api()
    
    try:
        # Try to get the service
        api_instance.read_namespaced_service(phpmyadmin_name, namespace)
        # If it exists, update it
        api_instance.patch_namespaced_service(
            name=phpmyadmin_name,
            namespace=namespace,
            body=service
        )
        
        return service, False
    except ApiException as e:
        if e.status == 404:
            # If it doesn't exist, create it
            api_instance.create_namespaced_service(
                namespace=namespace,
                body=service
            )
            
            return service, True
        else:
            # If there's another error, raise it
            raise e

def delete_phpmyadmin(name: str, namespace: str):
    """
    Delete phpMyAdmin deployment and service.
    
    Args:
        name: Name of the MySQL instance
        namespace: Namespace of the phpMyAdmin resources
    """
    phpmyadmin_name = f"{name}-phpmyadmin"
    
    # Delete deployment
    apps_api = client.AppsV1Api()
    try:
        apps_api.delete_namespaced_deployment(
            name=phpmyadmin_name,
            namespace=namespace
        )
    except ApiException as e:
        if e.status != 404:  # Ignore if already deleted
            raise e
    
    # Delete service
    core_api = client.CoreV1Api()
    try:
        core_api.delete_namespaced_service(
            name=phpmyadmin_name,
            namespace=namespace
        )
    except ApiException as e:
        if e.status != 404:  # Ignore if already deleted
            raise e 