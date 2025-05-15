import kopf
import logging
import kubernetes
import os
import sys

# Add the src directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('mysql-operator')

# Import handlers
from src.handlers.mysql import on_mysql_change, on_mysql_delete
from src.handlers.backup import on_backup_create, on_backup_delete

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    logger.info("Starting MySQL operator")
    
    # Configure operator
    settings.posting.level = logging.INFO
    
    # Configure Kubernetes client
    if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/token'):
        # In-cluster configuration
        kubernetes.config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes configuration")
    else:
        # Local development configuration
        try:
            kubernetes.config.load_kube_config()
            logger.info("Loaded local Kubernetes configuration")
        except kubernetes.config.config_exception.ConfigException as e:
            logger.error(f"Error loading Kubernetes configuration: {e}")
            raise kopf.PermanentError("Could not configure Kubernetes client")

# Run the operator
if __name__ == "__main__":
    kopf.run() 