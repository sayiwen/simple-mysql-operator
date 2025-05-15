import os

# Registry and version configuration
REGISTRY = os.environ.get("REGISTRY", "harbor.subat.cn/subat-mysql-operator")
VERSION = os.environ.get("VERSION", "8.0.35-1")
IMAGE_PULL_SECRET = os.environ.get("IMAGE_PULL_SECRET", "")

# Image names
MYSQL_IMAGE = "percona-server"
PHPMYADMIN_IMAGE = "phpmyadmin"
BACKUP_IMAGE = "backup"
RESTORE_IMAGE = "restore"

def get_mysql_image():
    """Get the MySQL image with registry and version."""
    return f"{REGISTRY}/{MYSQL_IMAGE}:{VERSION}"

def get_phpmyadmin_image():
    """Get the phpMyAdmin image with registry."""
    return f"{REGISTRY}/{PHPMYADMIN_IMAGE}:{VERSION}"

def get_backup_image():
    """Get the backup image with registry and version."""
    return f"{REGISTRY}/{BACKUP_IMAGE}:{VERSION}" 

def get_restore_image():
    """Get the restore image with registry and version."""
    return f"{REGISTRY}/{RESTORE_IMAGE}:{VERSION}" 

def get_image_pull_secret():
    """Get the image pull secret."""
    return IMAGE_PULL_SECRET
