from typing import Dict, List, Any, Optional

from kubernetes import client
from kubernetes.client.rest import ApiException

from ..utils.helpers import get_k8s_core_api

def create_mysql_pvc(
    name: str,
    namespace: str,
    storage_size: str,
    storage_class: Optional[str] = None,
    labels: Optional[Dict[str, str]] = None,
    owner_references: Optional[List[Dict[str, Any]]] = None
) -> client.V1PersistentVolumeClaim:
    """Create a PVC for MySQL data."""
    core_api = get_k8s_core_api()
    
    # Create the PVC
    pvc = client.V1PersistentVolumeClaim(
        api_version="v1",
        kind="PersistentVolumeClaim",
        metadata=client.V1ObjectMeta(
            name=f"{name}-data",
            namespace=namespace,
            labels=labels,
            owner_references=owner_references
        ),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            resources=client.V1ResourceRequirements(
                requests={"storage": storage_size}
            ),
            storage_class_name=storage_class
        )
    )
    
    try:
        # Check if PVC already exists
        existing_pvc = core_api.read_namespaced_persistent_volume_claim(f"{name}-data", namespace)
        # We don't update PVCs as they are immutable
    except ApiException as e:
        if e.status == 404:
            # Create if it doesn't exist
            core_api.create_namespaced_persistent_volume_claim(namespace, pvc)
        else:
            raise
    
    return pvc 