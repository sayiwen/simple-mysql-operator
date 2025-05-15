import kopf
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import croniter

from kubernetes.client.rest import ApiException

from src.utils.helpers import create_owner_reference, format_labels, get_secret_data
from src.resources.deployment import create_mysql_deployment
from src.resources.service import create_mysql_service
from src.resources.secret import create_mysql_secret
from src.resources.pvc import create_mysql_pvc
from src.resources.phpmyadmin import create_phpmyadmin_deployment, create_phpmyadmin_service, delete_phpmyadmin
from src.resources.backup import create_backup_cronjob, delete_backup_cronjob

@kopf.on.create('mysql.subat.cn', 'v1', 'simplemysqls')
@kopf.on.update('mysql.subat.cn', 'v1', 'simplemysqls')
async def on_mysql_change(spec, meta, status, body, patch, logger, **kwargs):
    name = meta['name']
    namespace = meta['namespace']
    
    logger.info(f"Processing SimpleMySql resource: {name} in namespace: {namespace}")
    
    # Extract database configuration
    database_config = spec.get('database', {})
    db_name = database_config.get('name', 'mysql')
    db_password = database_config.get('password')
    existing_secret = database_config.get('existingSecret')
    
    # Extract callback URL
    backup_callback_url = spec.get('callbackUrl', '')
    
    # Extract backup configuration
    backup_config = spec.get('backup', {})
    backup_enabled = backup_config.get('enabled', False)
    backup_schedule = backup_config.get('schedule', '0 2 * * *')
    backup_s3 = backup_config.get('s3', {})
    
    # Extract resource requirements
    resources = spec.get('resources', {})
    
    # Extract storage configuration
    storage_config = spec.get('storage', {})
    storage_size = storage_config.get('size', '10Gi')
    storage_class = storage_config.get('storageClass')
    
    # Extract node placement configuration
    node_selector = spec.get('nodeSelector')
    affinity = spec.get('affinity')
    tolerations = spec.get('tolerations')
    
    # Extract restore configuration
    restore_config = spec.get('restore')
    
    # Extract phpMyAdmin configuration
    phpmyadmin_config = spec.get('phpmyadmin', {})
    phpmyadmin_enabled = phpmyadmin_config.get('enabled', False)
    phpmyadmin_port = phpmyadmin_config.get('port', 8080)
    phpmyadmin_resources = phpmyadmin_config.get('resources', {})
    
    # Format labels for all resources
    labels = format_labels(name, 'mysql')
    
    # Create owner reference
    owner_ref = create_owner_reference(body)
    
    # Handle secret for credentials
    if existing_secret:
        # Use existing secret
        logger.info(f"Using existing secret: {existing_secret}")
        secret_name = existing_secret
        
        # Get existing secret data
        secret_data = get_secret_data(existing_secret, namespace)
        db_name = secret_data.get('MYSQL_DATABASE', db_name)
    else:
        # Create secret
        logger.info(f"Creating or updating secret for: {name}")
        secret, created = create_mysql_secret(
            name=name,
            namespace=namespace,
            db_name=db_name,
            password=db_password,
            callback_url=backup_callback_url,
            owner_references=[owner_ref]
        )
        secret_name = f"{name}-credentials"
        
        if created:
            logger.info(f"Secret {secret_name} created")
        else:
            logger.info(f"Secret {secret_name} updated")
    
    # Create PVC
    logger.info(f"Creating PVC for: {name}")
    pvc = create_mysql_pvc(
        name=name,
        namespace=namespace,
        storage_size=storage_size,
        storage_class=storage_class,
        labels=labels,
        owner_references=[owner_ref]
    )
    
    # Create Deployment
    logger.info(f"Creating Deployment for: {name}")
    deployment = create_mysql_deployment(
        name=name,
        namespace=namespace,
        storage_claim_name=f"{name}-data",
        secret_name=secret_name,
        db_name=db_name,
        labels=labels,
        resources=resources,
        node_selector=node_selector,
        affinity=affinity,
        tolerations=tolerations,
        owner_references=[owner_ref],
        restore_from_backup=restore_config
    )
    
    # Create Service
    logger.info(f"Creating Service for: {name}")
    service = create_mysql_service(
        name=name,
        namespace=namespace,
        labels=labels,
        owner_references=[owner_ref]
    )
    
    # Handle backup configuration
    if backup_enabled:
        logger.info(f"Setting up backup CronJob for MySQL instance: {name}")
        
        cronjob, created = create_backup_cronjob(
            name=name,
            namespace=namespace,
            schedule=backup_schedule,
            mysql_ref=name,
            s3_config=backup_s3,
            node_selector=node_selector,
            labels=labels,
            owner_references=[owner_ref]
        )
        
        if created:
            logger.info(f"Backup CronJob created for MySQL instance: {name}")
        else:
            logger.info(f"Backup CronJob updated for MySQL instance: {name}")
            
        # Update status with backup information
        # Calculate next backup time
        cron = croniter.croniter(backup_schedule, datetime.now())
        next_backup = cron.get_next(datetime)
        
        patch.status['nextBackup'] = next_backup.strftime("%Y-%m-%d %H:%M:%S")
    else:
        # If backup was enabled but is now disabled, delete the CronJob
        if status and status.get('nextBackup'):
            logger.info(f"Removing backup CronJob for MySQL instance: {name}")
            delete_backup_cronjob(name, namespace)
        
        # Remove backup information from status
        if 'nextBackup' in patch.status:
            patch.status['nextBackup'] = None
        if 'lastBackup' in patch.status:
            patch.status['lastBackup'] = None
    
    # Handle phpMyAdmin
    if phpmyadmin_enabled:
        logger.info(f"Setting up phpMyAdmin for MySQL instance: {name}")
        
        # Create phpMyAdmin deployment
        phpmyadmin_deployment, created = create_phpmyadmin_deployment(
            name=name,
            namespace=namespace,
            mysql_service_name=name,
            port=phpmyadmin_port,
            resources=phpmyadmin_resources,
            node_selector=node_selector,
            owner_references=[owner_ref]
        )
        
        if created:
            logger.info(f"phpMyAdmin deployment created for MySQL instance: {name}")
        else:
            logger.info(f"phpMyAdmin deployment updated for MySQL instance: {name}")
        
        # Create phpMyAdmin service
        phpmyadmin_service, created = create_phpmyadmin_service(
            name=name,
            namespace=namespace,
            port=phpmyadmin_port,
            owner_references=[owner_ref]
        )
        
        if created:
            logger.info(f"phpMyAdmin service created for MySQL instance: {name}")
        else:
            logger.info(f"phpMyAdmin service updated for MySQL instance: {name}")
        
        # Update status with phpMyAdmin URL
        patch.status['phpmyadminUrl'] = f"http://{name}-phpmyadmin.{namespace}.svc.cluster.local:{phpmyadmin_port}"
    else:
        # If phpMyAdmin was enabled but is now disabled, delete the resources
        if status and status.get('phpmyadminUrl'):
            logger.info(f"Removing phpMyAdmin resources for MySQL instance: {name}")
            delete_phpmyadmin(name, namespace)
        
        # Remove phpMyAdmin URL from status
        if 'phpmyadminUrl' in patch.status:
            patch.status['phpmyadminUrl'] = None
    
    # Update status
    patch.status['phase'] = 'Running'
    patch.status['message'] = 'MySQL instance is running'
    patch.status['ready'] = True
    patch.status['dbHost'] = name
    patch.status['dbPort'] = '3306'
    patch.status['secretName'] = secret_name
    
    logger.info(f"SimpleMySql {name} successfully processed")
    
    return {'secretName': secret_name}

@kopf.on.delete('mysql.subat.cn', 'v1', 'simplemysqls')
async def on_mysql_delete(spec, meta, status, logger, **kwargs):
    name = meta['name']
    namespace = meta['namespace']
    
    logger.info(f"SimpleMySql resource {name} in namespace {namespace} is being deleted. "
                f"Related resources with owner references will be garbage-collected.")
    
    # Note: Kubernetes garbage collection will handle resources with owner references 