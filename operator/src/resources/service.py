from typing import Dict, List, Any

from kubernetes import client
from kubernetes.client.rest import ApiException

from ..utils.helpers import get_k8s_core_api, format_labels

def create_mysql_service(
    name: str,
    namespace: str,
    labels: Dict[str, str],
    owner_references: List[Dict[str, Any]] = None
) -> client.V1Service:
    """Create a MySQL service."""
    core_api = get_k8s_core_api()
    
    # Create the service
    service = client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels=labels,
            owner_references=owner_references
        ),
        spec=client.V1ServiceSpec(
            selector=labels,
            ports=[
                client.V1ServicePort(
                    port=3306,
                    target_port=3306,
                    name="mysql"
                )
            ]
        )
    )
    
    try:
        # Check if service already exists
        existing_service = core_api.read_namespaced_service(name, namespace)
        # Update if it exists
        core_api.replace_namespaced_service(name, namespace, service)
    except ApiException as e:
        if e.status == 404:
            # Create if it doesn't exist
            core_api.create_namespaced_service(namespace, service)
        else:
            raise
    
    return service 