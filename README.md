# MySQL Operator

A Kubernetes operator for deploying and managing MySQL instances and backups.

## Features

- Deploy SimpleMySql resources to create MySQL instances
- Create SimpleMySqlBackup resources to run backups to S3-compatible storage
- Automatic secret generation or use existing secrets
- Optional phpMyAdmin integration with configurable resources
- Support for resource limits, node selectors, affinity, and tolerations
- Restore from backup during deployment
- Automatic cleanup of completed backup jobs and resources
- Scheduled backups with configurable retention policies
- Callback URL support for backup notifications

## Installation

### Prerequisites

- Kubernetes cluster 1.16+
- kubectl configured to communicate with your cluster

### Install the CRDs

```bash
kubectl apply -f manifests/crds/
```

### Install the operator

```bash
kubectl apply -f manifests/rbac/
kubectl apply -f manifests/deployment.yaml
```

## Usage

### Deploy a MySQL instance

```yaml
apiVersion: mysql.subat.cn/v1
kind: SimpleMySql
metadata:
  name: example-mysql
  namespace: default
spec:
  database:
    name: mydb
  resources:
    requests:
      memory: "512Mi"
      cpu: "500m"
    limits:
      memory: "1Gi"
      cpu: "1000m"
  storage:
    size: 10Gi
```

### Deploy MySQL with phpMyAdmin

```yaml
apiVersion: mysql.subat.cn/v1
kind: SimpleMySql
metadata:
  name: example-mysql-phpmyadmin
  namespace: default
spec:
  database:
    name: mydb
  storage:
    size: 10Gi
  phpmyadmin:
    enabled: true
    port: 8080
    resources:
      requests:
        memory: "128Mi"
        cpu: "100m"
      limits:
        memory: "256Mi"
        cpu: "200m"
```

### Configure scheduled backups

```yaml
apiVersion: mysql.subat.cn/v1
kind: SimpleMySql
metadata:
  name: mysql-with-backups
  namespace: default
spec:
  database:
    name: mydb
  storage:
    size: 10Gi
  backup:
    enabled: true
    schedule: "0 2 * * *"  # Daily at 2am
    s3:
      bucket: "your-bucket"
      endpoint: "https://s3.example.com"
      prefix: "mysql/backups"
      secretRef: "s3-credentials"
      keepDays: 7
  callbackUrl: "https://webhook.example.com/backup-complete"
```

### Create a one-time backup

```yaml
apiVersion: mysql.subat.cn/v1
kind: SimpleMySqlBackup
metadata:
  name: mysql-backup
  namespace: default
spec:
  mysqlRef: example-mysql
  ttlSecondsAfterFinished: 86400  # Cleanup Job after 1 day (default)
  retentionDays: 7  # Auto-delete backup resource after 7 days (default)
  s3:
    bucket: "your-bucket"
    endpoint: "https://s3.example.com"
    prefix: "mysql/backups"
    secretRef: "s3-credentials"
    keepDays: 7
```

### Deploy a MySQL instance with restore from backup

```yaml
apiVersion: mysql.subat.cn/v1
kind: SimpleMySql
metadata:
  name: restored-mysql
  namespace: default
spec:
  database:
    name: mydb
  storage:
    size: 10Gi
  restore:
    backupId: "20230101120000"  # Optional, uses latest if not specified
    s3:
      bucket: "your-bucket"
      endpoint: "https://s3.example.com"
      prefix: "mysql/backups"
      secretRef: "s3-credentials"
```

### Use existing secrets

```yaml
apiVersion: mysql.subat.cn/v1
kind: SimpleMySql
metadata:
  name: mysql-existing-secret
  namespace: default
spec:
  database:
    name: mydb
    existingSecret: "mysql-credentials"  # Secret should contain 'password' key
  storage:
    size: 10Gi
```

### Advanced node placement

```yaml
apiVersion: mysql.subat.cn/v1
kind: SimpleMySql
metadata:
  name: mysql-placement
  namespace: default
spec:
  database:
    name: mydb
  storage:
    size: 10Gi
  nodeSelector:
    disk-type: ssd
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: kubernetes.io/os
            operator: In
            values:
            - linux
  tolerations:
  - key: "database"
    operator: "Equal"
    value: "true"
    effect: "NoSchedule"
```

## Images

The operator uses the following images from the configured registry:

- `percona-server` - MySQL database server (Percona Server distribution)
- `phpmyadmin` - Web interface for MySQL management
- `backup` - Custom image for running backups to S3
- `restore` - Custom image for restoring from S3 backups

The registry and version are configured through environment variables in the operator deployment:

```yaml
env:
  - name: REGISTRY
    value: harbor.subat.cn/subat-mysql-operator
  - name: VERSION
    value: 8.0.35-1
```

## Building

Build the operator and required images:

```bash
cd images && docker build -t harbor.subat.cn/subat-mysql-operator/percona-server:8.0.35-1 -f Dockerfile.mysql .
cd images && docker build -t harbor.subat.cn/subat-mysql-operator/phpmyadmin:8.0.35-1 -f Dockerfile.phpmyadmin .
cd images && docker build -t harbor.subat.cn/subat-mysql-operator/backup:8.0.35-1 -f Dockerfile.backup .
cd images && docker build -t harbor.subat.cn/subat-mysql-operator/restore:8.0.35-1 -f Dockerfile.restore .
docker build -t harbor.subat.cn/subat-mysql-operator/operator:8.0.35-1 .
```

## Development

### Local development setup

The operator requires Python 3.9. You can use the provided setup script to create a virtual environment:

```bash
# Run the setup script
./setup.sh

# Or manually set up the environment
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Running the operator locally

```bash
source venv/bin/activate
cd src
python main.py --verbose
```

### Common issues

If you encounter errors related to Python version compatibility:

1. Make sure you're using Python 3.9 (the same version specified in the Dockerfile)
2. Create a fresh virtual environment with Python 3.9
3. Install the exact package versions specified in requirements.txt

## License

MIT