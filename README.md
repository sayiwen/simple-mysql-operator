# MySQL Operator

用于部署和管理 单实例MySQL与备份的 Kubernetes Operator

## 功能特性

- 部署 SimpleMySql 资源以创建 MySQL 实例
- 创建 SimpleMySqlBackup 资源以执行备份到 S3 兼容存储
- 自动密钥生成或使用现有密钥
- 可选的 phpMyAdmin 集成，支持资源配置
- 支持资源限制、节点选择器、亲和性和容忍度设置
- 部署时从备份恢复
- 自动清理已完成的备份作业和资源
- 支持计划备份与可配置的保留策略
- 支持备份通知的回调 URL

## 安装

### 前提条件

- Kubernetes 集群 1.16+
- kubectl 已配置为与您的集群通信

### 安装 CRD

```bash
kubectl apply -f manifests/crds/
```

### 安装操作器

```bash
kubectl apply -f manifests/rbac/
kubectl apply -f manifests/deployment.yaml
```

## 使用方法

### 部署 MySQL 实例

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

### 部署带有 phpMyAdmin 的 MySQL

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

### 配置计划备份

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
    schedule: "0 2 * * *"  # 每天凌晨2点
    s3:
      bucket: "your-bucket"
      endpoint: "https://s3.example.com"
      prefix: "mysql/backups"
      secretRef: "s3-credentials"
      keepDays: 7
  callbackUrl: "https://webhook.example.com/backup-complete"
```

### 创建一次性备份

```yaml
apiVersion: mysql.subat.cn/v1
kind: SimpleMySqlBackup
metadata:
  name: mysql-backup
  namespace: default
spec:
  mysqlRef: example-mysql
  ttlSecondsAfterFinished: 86400  # 作业完成后1天清理（默认）
  retentionDays: 7  # 7天后自动删除备份资源（默认）
  s3:
    bucket: "your-bucket"
    endpoint: "https://s3.example.com"
    prefix: "mysql/backups"
    secretRef: "s3-credentials"
    keepDays: 7
```

### 从备份恢复部署 MySQL 实例

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
    backupId: "20230101120000"  # 可选，如未指定则使用最新备份
    s3:
      bucket: "your-bucket"
      endpoint: "https://s3.example.com"
      prefix: "mysql/backups"
      secretRef: "s3-credentials"
```

### 使用现有密钥

```yaml
apiVersion: mysql.subat.cn/v1
kind: SimpleMySql
metadata:
  name: mysql-existing-secret
  namespace: default
spec:
  database:
    name: mydb
    existingSecret: "mysql-credentials"  # 密钥应包含'password'键
  storage:
    size: 10Gi
```

### 高级节点放置

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

## 镜像

操作器使用以下来自配置注册表的镜像：

- `percona-server` - MySQL 数据库服务器（Percona Server 发行版）
- `phpmyadmin` - MySQL 管理的 Web 界面
- `backup` - 用于执行备份到 S3 的自定义镜像
- `restore` - 用于从 S3 备份恢复的自定义镜像

注册表和版本通过操作器部署中的环境变量配置：

```yaml
env:
  - name: REGISTRY
    value: harbor.subat.cn/subat-mysql-operator
  - name: VERSION
    value: 8.0.35-1
```

## 构建

构建操作器和所需镜像：

```bash
cd images && docker build -t harbor.subat.cn/subat-mysql-operator/percona-server:8.0.35-1 -f Dockerfile.mysql .
cd images && docker build -t harbor.subat.cn/subat-mysql-operator/phpmyadmin:8.0.35-1 -f Dockerfile.phpmyadmin .
cd images && docker build -t harbor.subat.cn/subat-mysql-operator/backup:8.0.35-1 -f Dockerfile.backup .
cd images && docker build -t harbor.subat.cn/subat-mysql-operator/restore:8.0.35-1 -f Dockerfile.restore .
docker build -t harbor.subat.cn/subat-mysql-operator/operator:8.0.35-1 .
```

## 开发

### 本地开发环境设置

操作器需要 Python 3.9。您可以使用提供的设置脚本创建虚拟环境：

```bash
# 运行设置脚本
./setup.sh

# 或手动设置环境
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 本地运行操作器

```bash
source venv/bin/activate
cd src
python main.py --verbose
```

### 常见问题

如果遇到与 Python 版本兼容性相关的错误：

1. 确保您使用的是 Python 3.9（与 Dockerfile 中指定的版本相同）
2. 使用 Python 3.9 创建一个新的虚拟环境
3. 安装 requirements.txt 中指定的确切软件包版本

## 许可证

MIT