# MySQL 备份与恢复工具

该工具集提供了一套完整的 MySQL 备份与恢复解决方案，专为 Docker 环境设计，使用 Percona XtraBackup 进行物理备份，并支持将备份上传到 S3 兼容存储或阿里云 OSS。

## 镜像说明

本项目提供两个独立的 Docker 镜像：

1. **备份镜像 (`harbor.subat.cn/subat-mysql-operator/backup:8.0.35-1`)**
   - 用于执行 MySQL 数据库备份并上传到对象存储
   - 基于 Percona XtraBackup 8.0.35

2. **恢复镜像 (`harbor.subat.cn/subat-mysql-operator/restore:8.0.35-1`)**
   - 用于从对象存储下载备份并恢复数据
   - 基于 Percona XtraBackup 8.0.35

## 目录规范

工具使用以下固定目录:

- `/var/lib/mysql` - MySQL 数据目录（备份时需挂载）
- `/app/restore` - 恢复目标目录（恢复时需挂载）
- `/tmp` - 备份临时目录

## 备份镜像使用方法

### 配置参数

| 参数名称 | 默认值 | 说明 |
|----------|--------|------|
| S3_BUCKET | example-bucket | 存储桶名称 |
| S3_ENDPOINT | https://example.com | 存储服务端点 |
| S3_ACCESS_KEY | ********** | 访问密钥 ID |
| S3_SECRET_KEY | ********** | 访问密钥秘钥 |
| S3_PREFIX | default | 存储桶内的前缀路径 |
| S3_KEEP_DAYS | 7 | S3 备份保留天数 |
| MYSQL_HOST | host.docker.internal | MySQL 主机地址 |
| MYSQL_PORT | 3306 | MySQL 端口 |
| MYSQL_USER | root | MySQL 用户名 |
| MYSQL_PASSWORD | ******** | MySQL 密码 |
| SKIP_BACKUP | 0 | 设置为1跳过实际备份，创建测试文件 |
| CALLBACK_URL | "" | 备份完成后的回调URL，会以POST方式发送backup_name参数 |

### Docker 运行示例

```bash
# 直接从MySQL备份
docker run \
  -v /var/lib/mysql:/var/lib/mysql \
  -e MYSQL_HOST=mysql-host \
  -e MYSQL_PASSWORD=your-password \
  -e S3_BUCKET=your-bucket \
  -e S3_ENDPOINT=your-endpoint \
  -e S3_ACCESS_KEY=your-access-key \
  -e S3_SECRET_KEY=your-secret-key \
  -e S3_PREFIX=mysql/backups \
  -e CALLBACK_URL=https://your-callback-url \
  harbor.subat.cn/subat-mysql-operator/backup:8.0.35-1

```

## 恢复镜像使用方法

### 配置参数

| 参数名称 | 默认值 | 说明 |
|----------|--------|------|
| S3_BUCKET | example-bucket | 存储桶名称 |
| S3_ENDPOINT | https://example.com | 存储服务端点 |
| S3_ACCESS_KEY | ********** | 访问密钥 ID |
| S3_SECRET_KEY | ********** | 访问密钥秘钥 |
| S3_PREFIX | default | 存储桶内的前缀路径 |
| BACKUP_ID | "" | 指定要恢复的备份ID（时间戳部分），不指定则使用最新备份 |

### Docker 运行示例

```bash
# 恢复最新备份
docker run \
  -v /path/to/restore:/app/restore \
  -e S3_BUCKET=your-bucket \
  -e S3_ENDPOINT=your-endpoint \
  -e S3_ACCESS_KEY=your-access-key \
  -e S3_SECRET_KEY=your-secret-key \
  -e S3_PREFIX=mysql/backups \
  harbor.subat.cn/subat-mysql-operator/restore:8.0.35-1

# 恢复指定ID的备份
docker run \
  -v /path/to/restore:/app/restore \
  -e S3_BUCKET=your-bucket \
  -e S3_ENDPOINT=your-endpoint \
  -e S3_ACCESS_KEY=your-access-key \
  -e S3_SECRET_KEY=your-secret-key \
  -e BACKUP_ID=20250514124456 \
  harbor.subat.cn/subat-mysql-operator/restore:8.0.35-1
```

## Kubernetes 部署示例

### 创建备份 CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: mysql-backup
spec:
  schedule: "0 2 * * *"  # 每天凌晨2点执行
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: harbor.subat.cn/subat-mysql-operator/backup:8.0.35-1
            env:
            - name: MYSQL_HOST
              value: "mysql.database.svc.cluster.local"
            - name: MYSQL_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: mysql-credentials
                  key: password
            - name: S3_BUCKET
              value: "your-bucket"
            - name: S3_ENDPOINT
              value: "your-endpoint"
            - name: S3_PREFIX
              value: "mysql/prod"
            - name: S3_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: s3-credentials
                  key: access-key
            - name: S3_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: s3-credentials
                  key: secret-key
            - name: CALLBACK_URL
              value: "https://your-webhook-endpoint/backup-complete"
          restartPolicy: OnFailure
```

### 恢复备份的 Job

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: mysql-restore
spec:
  template:
    spec:
      containers:
      - name: restore
        image: harbor.subat.cn/subat-mysql-operator/restore:8.0.35-1
        env:
        - name: S3_BUCKET
          value: "your-bucket"
        - name: S3_ENDPOINT
          value: "your-endpoint"
        - name: S3_PREFIX
          value: "mysql/prod"
        - name: S3_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: s3-credentials
              key: access-key
        - name: S3_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: s3-credentials
              key: secret-key
        # 可选：指定备份ID
        # - name: BACKUP_ID
        #   value: "20250514124456"
        volumeMounts:
        - name: mysql-data
          mountPath: /app/restore
      volumes:
      - name: mysql-data
        persistentVolumeClaim:
          claimName: mysql-data-pvc
      restartPolicy: Never
```

## 注意事项

1. 备份镜像需要能够连接到 MySQL 服务器或挂载 MySQL 数据目录
2. 恢复镜像需要挂载一个可写入的目录到 `/data`
3. 恢复操作会替换目标目录中的现有数据，请谨慎操作
4. 密码等敏感信息建议通过环境变量传递
5. 备份文件格式为 `${S3_PREFIX}/backup_YYYYMMDDHHMMSS.tar.gz`
