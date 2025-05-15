from typing import Dict, List, Any, Optional, Tuple

from kubernetes import client
from kubernetes.client.rest import ApiException

from ..utils.helpers import get_k8s_core_api, generate_password, create_or_update_secret

def create_mysql_secret(
    name: str,
    namespace: str,
    db_name: str,
    password: Optional[str] = None,
    callback_url: Optional[str] = None,
    owner_references: Optional[List[Dict[str, Any]]] = None
) -> Tuple[client.V1Secret, bool]:
    """
    Create a secret for MySQL with credentials.
    Returns the created secret and a boolean indicating if it was newly created.
    
    Args:
        name: MySQL instance name
        namespace: Kubernetes namespace
        db_name: Database name
        password: MySQL root password (auto-generated if None)
        callback_url: URL to call after backup completion (from backup.callbackUrl)
        owner_references: K8s owner references for the secret
    """
    # Generate password if not provided
    if password is None:
        password = generate_password()
    
    # Prepare secret data
    secret_data = {
        "MYSQL_HOST": f"{name}",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": password,
        "MYSQL_DATABASE": db_name,
        "MYSQL_ROOT_HOST": "%",  # Allow connections from any host
        "CALLBACK_URL": callback_url or ""  # Use provided callback URL or empty string
    }
    
    # Create or update the secret
    return create_or_update_secret(
        name=f"{name}-credentials",
        namespace=namespace,
        data=secret_data,
        owner_references=owner_references
    ) 