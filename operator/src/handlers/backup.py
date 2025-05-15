import kopf
import logging
import datetime
from typing import Dict, Any, Optional
import time

from kubernetes.client.rest import ApiException
from kubernetes import client

from src.utils.helpers import create_owner_reference, format_labels, get_secret_data
from src.resources.job import create_backup_job

@kopf.on.create('mysql.subat.cn', 'v1', 'simplemysqlbackups')
async def on_backup_create(spec, meta, status, body, patch, logger, **kwargs):
    name = meta['name']
    namespace = meta['namespace']
    
    logger.info(f"Processing SimpleMySqlBackup resource: {name} in namespace: {namespace}")
    
    # Extract MySQL reference and S3 configuration
    mysql_ref = spec.get('mysqlRef')
    s3_config = spec.get('s3', {})
    
    # Extract TTL for job cleanup
    ttl_seconds_after_finished = spec.get('ttlSecondsAfterFinished', 30)  # Default: 1 day
    
    if not mysql_ref:
        error_msg = f"SimpleMySqlBackup {name} is missing required field 'mysqlRef'"
        logger.error(error_msg)
        raise kopf.PermanentError(error_msg)
    
    if not s3_config:
        error_msg = f"SimpleMySqlBackup {name} is missing required field 's3'"
        logger.error(error_msg)
        raise kopf.PermanentError(error_msg)
    
    # Validate required S3 configuration
    required_s3_fields = ['bucket', 'endpoint', 'secretRef']
    missing_fields = [field for field in required_s3_fields if field not in s3_config]
    
    if missing_fields:
        error_msg = f"SimpleMySqlBackup {name} is missing required S3 fields: {', '.join(missing_fields)}"
        logger.error(error_msg)
        raise kopf.PermanentError(error_msg)
    
    # Try to get the referenced MySQL resource to use its node selector
    node_selector = None
    try:
        api_instance = client.CustomObjectsApi()
        mysql_resource = api_instance.get_namespaced_custom_object(
            group="mysql.subat.cn",
            version="v1",
            namespace=namespace,
            plural="simplemysqls",
            name=mysql_ref
        )
        
        # Extract node selector from MySQL resource
        if mysql_resource and "spec" in mysql_resource:
            node_selector = mysql_resource["spec"].get("nodeSelector")
            logger.info(f"Using node selector from MySQL resource: {node_selector}")
    except ApiException as e:
        logger.warning(f"Could not retrieve MySQL resource {mysql_ref}: {e}. Will proceed without node selector.")
    
    # Format labels for the backup job
    labels = format_labels(name, 'backup')
    
    # Create owner reference
    owner_ref = create_owner_reference(body)
    
    # Start time for the backup
    start_time = datetime.datetime.now().isoformat()
    
    # Create backup job
    logger.info(f"Creating backup job for MySQL instance: {mysql_ref}")
    try:
        job = create_backup_job(
            name=name,
            namespace=namespace,
            mysql_ref=mysql_ref,
            s3_config=s3_config,
            labels=labels,
            node_selector=node_selector,
            owner_references=[owner_ref],
            ttl_seconds_after_finished=ttl_seconds_after_finished
        )
        
        # Update status
        backup_id = job.metadata.name.split('-')[-1]  # Extract backup ID from job name
        patch.status['phase'] = 'Running'
        patch.status['message'] = f'Backup job created for {mysql_ref}'
        patch.status['backupId'] = backup_id
        patch.status['startTime'] = start_time
        patch.status['jobName'] = job.metadata.name
        
        logger.info(f"Backup job {job.metadata.name} created with backup ID: {backup_id}")
        
        return {'backupId': backup_id}
    
    except ApiException as e:
        error_msg = f"Failed to create backup job: {e}"
        logger.error(error_msg)
        patch.status['phase'] = 'Failed'
        patch.status['message'] = error_msg
        raise kopf.PermanentError(error_msg)

@kopf.on.delete('mysql.subat.cn', 'v1', 'simplemysqlbackups')
async def on_backup_delete(spec, meta, status, logger, **kwargs):
    name = meta['name']
    namespace = meta['namespace']
    
    logger.info(f"SimpleMySqlBackup resource {name} in namespace {namespace} is being deleted. "
                f"Related backup job resources with owner references will be garbage-collected.")
    
    # Note: The actual backup data in S3 is not deleted 

@kopf.timer('mysql.subat.cn', 'v1', 'simplemysqlbackups', interval=3600)  # Run every hour
async def cleanup_completed_backups(logger, **kwargs):
    """
    Periodically check and clean up completed backup resources.
    This timer runs every hour and cleans up backup resources that:
    1. Have completed successfully (job status is "Succeeded")
    2. Have been completed for more than the specified retention period
    """
    logger.info("Running scheduled cleanup of completed backup resources")
    
    try:
        # Get all SimpleMySqlBackup resources
        api = client.CustomObjectsApi()
        backups = api.list_cluster_custom_object(
            group="mysql.subat.cn",
            version="v1",
            plural="simplemysqlbackups"
        )
        
        batch_api = client.BatchV1Api()
        
        # Current time for comparison
        current_time = datetime.datetime.now()
        
        for backup in backups.get('items', []):
            name = backup['metadata']['name']
            namespace = backup['metadata']['namespace']
            status = backup.get('status', {})
            
            # Skip if no status yet
            if not status:
                continue
                
            # Skip if no job name in status
            job_name = status.get('jobName')
            if not job_name:
                continue
            
            # Check if the job exists and its status
            try:
                job = batch_api.read_namespaced_job(job_name, namespace)
                
                # If job is completed
                if job.status.succeeded:
                    # Get completion time
                    completion_time = None
                    for condition in job.status.conditions or []:
                        if condition.type == "Complete" and condition.status == "True":
                            completion_time = condition.last_transition_time
                            break
                    
                    if completion_time:
                        # Parse completion time
                        completion_time = completion_time.replace(tzinfo=None)
                        
                        # Get retention period from spec (default to 7 days if not specified)
                        retention_days = backup.get('spec', {}).get('retentionDays', 3)
                        retention_seconds = retention_days * 86400
                        
                        # Check if retention period has passed
                        elapsed = (current_time - completion_time).total_seconds()
                        if elapsed > retention_seconds:
                            logger.info(f"Cleaning up completed backup {name} in namespace {namespace} "
                                       f"(completed {elapsed/86400:.1f} days ago)")
                            
                            # Delete the backup resource
                            api.delete_namespaced_custom_object(
                                group="mysql.subat.cn",
                                version="v1",
                                plural="simplemysqlbackups",
                                namespace=namespace,
                                name=name
                            )
            except ApiException as e:
                if e.status == 404:
                    # Job not found, might have been cleaned up already
                    logger.info(f"Job {job_name} for backup {name} not found, might have been cleaned up already")
                else:
                    logger.error(f"Error checking job {job_name} for backup {name}: {e}")
    
    except ApiException as e:
        logger.error(f"Error during backup cleanup: {e}") 