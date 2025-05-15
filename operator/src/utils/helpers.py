import base64
import os
import random
import string
import secrets
from typing import Dict, Any, Optional, Tuple

from kubernetes import client
from kubernetes.client.rest import ApiException

def get_k8s_core_api() -> client.CoreV1Api:
    """Get Kubernetes Core API client."""
    return client.CoreV1Api()

def get_k8s_apps_api() -> client.AppsV1Api:
    """Get Kubernetes Apps API client."""
    return client.AppsV1Api()

def get_k8s_batch_api() -> client.BatchV1Api:
    """Get Kubernetes Batch API client for Jobs and CronJobs."""
    return client.BatchV1Api()

def generate_password(length: int = 16) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def create_or_update_secret(
    name: str,
    namespace: str,
    data: Dict[str, str],
    owner_references: Optional[list] = None
) -> Tuple[client.V1Secret, bool]:
    """Create or update a Kubernetes secret."""
    core_api = get_k8s_core_api()
    encoded_data = {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}
    
    secret = client.V1Secret(
        api_version="v1",
        kind="Secret",
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            owner_references=owner_references
        ),
        data=encoded_data
    )
    
    created = False
    try:
        # Try to get existing secret
        existing_secret = core_api.read_namespaced_secret(name, namespace)
        # Update if exists
        core_api.replace_namespaced_secret(name, namespace, secret)
    except ApiException as e:
        if e.status == 404:
            # Create if doesn't exist
            core_api.create_namespaced_secret(namespace, secret)
            created = True
        else:
            raise
    
    return secret, created

def get_secret_data(secret_name: str, namespace: str) -> Dict[str, str]:
    """Get decoded data from a Kubernetes secret."""
    core_api = get_k8s_core_api()
    
    try:
        secret = core_api.read_namespaced_secret(secret_name, namespace)
        return {k: base64.b64decode(v).decode() for k, v in secret.data.items()}
    except ApiException as e:
        if e.status == 404:
            return {}
        raise

def create_owner_reference(resource):
    """Create owner reference for dependent objects."""
    return client.V1OwnerReference(
        api_version=resource["apiVersion"],
        kind=resource["kind"],
        name=resource["metadata"]["name"],
        uid=resource["metadata"]["uid"],
        block_owner_deletion=True,
        controller=True,
    )

def format_labels(name: str, component: str) -> Dict[str, str]:
    """Format standard labels for resources."""
    return {
        "app": "simplemysql",
        "instance": name,
        "component": component,
        "managed-by": "mysql-operator"
    } 