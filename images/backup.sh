#!/bin/bash

# 将所有环境变量写入 /app/env 文件
env > /app/env

# 默认配置
S3_BUCKET="example-bucket"
S3_ENDPOINT="https://example.com"
S3_ACCESS_KEY="**********"
S3_SECRET_KEY="**********"
S3_PREFIX="default"
S3_TYPE="" # aliyun或留空表示S3兼容存储
SKIP_BACKUP=0 # 设置为1跳过备份，仅测试上传
S3_KEEP_DAYS=7 # 保留天数
CALLBACK_URL=""

MYSQL_HOST="host.docker.internal"
MYSQL_PORT="3306"
MYSQL_USER="root"
MYSQL_PASSWORD="********"

# 备份目录
BACKUP_DIR="/app/backup"
# 源目录
SOURCE_DIR="/var/lib/mysql"

# 备份文件名
DATE=$(date +%Y%m%d%H%M%S)
BACKUP_NAME="backup_${DATE}"

# 加载环境变量配置
if [ -f /app/env ]; then
  source /app/env
fi

# 使用环境变量覆盖默认值
[ -n "$S3_BUCKET" ] && S3_BUCKET="$S3_BUCKET"
[ -n "$S3_ENDPOINT" ] && S3_ENDPOINT="$S3_ENDPOINT"
[ -n "$S3_ACCESS_KEY" ] && S3_ACCESS_KEY="$S3_ACCESS_KEY"
[ -n "$S3_SECRET_KEY" ] && S3_SECRET_KEY="$S3_SECRET_KEY"
[ -n "$S3_PREFIX" ] && S3_PREFIX="$S3_PREFIX"
[ -n "$SKIP_BACKUP" ] && SKIP_BACKUP="$SKIP_BACKUP"
[ -n "$S3_KEEP_DAYS" ] && S3_KEEP_DAYS="$S3_KEEP_DAYS"

[ -n "$MYSQL_HOST" ] && MYSQL_HOST="$MYSQL_HOST"
[ -n "$MYSQL_PORT" ] && MYSQL_PORT="$MYSQL_PORT"
[ -n "$MYSQL_USER" ] && MYSQL_USER="$MYSQL_USER"
[ -n "$MYSQL_PASSWORD" ] && MYSQL_PASSWORD="$MYSQL_PASSWORD"



# 判断是否为阿里云OSS
if [[ "$S3_ENDPOINT" == *"aliyuncs"* ]]; then
  S3_TYPE="aliyun"
fi


# 检查必需变量
check_requirements() {
  if [ -z "$S3_BUCKET" ] || [ -z "$S3_ACCESS_KEY" ] || [ -z "$S3_SECRET_KEY" ]; then
    echo "错误: S3_BUCKET, S3_ACCESS_KEY, 和 S3_SECRET_KEY 必须设置。" >&2
    exit 1
  fi
  # 创建备份目录
  mkdir -p "$BACKUP_DIR"
}

# 执行数据库备份
perform_backup() {
  if [ "$SKIP_BACKUP" -eq 1 ]; then
    echo "跳过实际备份，创建测试文件"
    echo "这是一个S3上传测试文件" > "$BACKUP_DIR/$BACKUP_NAME.tar.gz"
    return 0
  fi
  
  # 执行备份
  echo "开始备份到 $BACKUP_DIR/$BACKUP_NAME"
  xtrabackup --backup --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" --password="$MYSQL_PASSWORD" --target-dir="$BACKUP_DIR/$BACKUP_NAME"
  
  if [ $? -ne 0 ]; then
    echo "备份失败！" >&2
    exit 1
  fi
  
  # 准备备份
  echo "准备备份"
  xtrabackup --prepare --target-dir="$BACKUP_DIR/$BACKUP_NAME"
  
  if [ $? -ne 0 ]; then
    echo "准备失败！" >&2
    exit 1
  fi
  
  # 压缩备份
  echo "压缩备份"
  tar czvf "$BACKUP_DIR/$BACKUP_NAME.tar.gz" -C "$BACKUP_DIR" "$BACKUP_NAME"
  
  if [ $? -ne 0 ]; then
    echo "压缩失败！" >&2
    exit 1
  fi
}

# 配置存储凭证
setup_auth() {
  if [[ "$S3_TYPE" == "aliyun" ]]; then
    echo "配置 Aliyun OSS 的 ossutil"
    config_file="/tmp/.ossutilconfig"
    cat > "$config_file" << EOF
[Credentials]
language=EN
endpoint=$S3_ENDPOINT
accessKeyID=$S3_ACCESS_KEY
accessKeySecret=$S3_SECRET_KEY
EOF
  else
    echo "使用 MinIO 客户端 S3 配置"
    mkdir -p "/tmp/.mc"
    mc --config-dir "/tmp/.mc" alias set s3 "$S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY"
  fi
}

# 上传备份到存储
upload_backup() {
  if [[ "$S3_TYPE" == "aliyun" ]]; then
    # 创建检查点目录
    checkpoint_dir="/tmp/.ossutil_checkpoint_${DATE}"
    mkdir -p "$checkpoint_dir"
    
    # 使用 ossutil 上传文件
    echo "使用 ossutil 上传..."
    ossutil -c "/tmp/.ossutilconfig" cp "$BACKUP_DIR/$BACKUP_NAME.tar.gz" "oss://$S3_BUCKET/$S3_PREFIX/$BACKUP_NAME.tar.gz" --checkpoint-dir="$checkpoint_dir" --force
    
    if [ $? -ne 0 ]; then
      echo "上传到 OSS 存储失败！" >&2
      exit 1
    fi
  else
    # 使用 mc 上传文件
    echo "使用 mc 上传..."
    mc --config-dir "/tmp/.mc" cp "$BACKUP_DIR/$BACKUP_NAME.tar.gz" "s3/$S3_BUCKET/$S3_PREFIX/$BACKUP_NAME.tar.gz"
    
    if [ $? -ne 0 ]; then
      echo "上传到 S3 存储失败！" >&2
      exit 1
    fi
  fi
  
  echo "备份上传成功: $BACKUP_NAME.tar.gz"

  if [ -n "$CALLBACK_URL" ]; then
    echo "回调: $CALLBACK_URL"
    result=$(curl -X POST "$CALLBACK_URL" -d "backup_name=$BACKUP_NAME" --max-time 10 --retry 3 --retry-delay 1 --retry-max-time 60)
    echo "回调结果: $result"
  fi
}

# 清理本地备份文件
cleanup() {
  echo "清理本地备份文件"
  rm -rf "$BACKUP_DIR/$BACKUP_NAME" "$BACKUP_DIR/$BACKUP_NAME.tar.gz"
  echo "清理远程备份文件"
  echo "清理${S3_KEEP_DAYS}天前的远程备份文件"
  
  keep_days_ago=$(date -d "$S3_KEEP_DAYS days ago" +%Y%m%d)

  if [[ "$S3_TYPE" == "aliyun" ]]; then
    # 列出所有备份文件
    backup_list=$(ossutil -c "/tmp/.ossutilconfig" ls "oss://$S3_BUCKET/$S3_PREFIX/" | grep -E "backup_[0-9]+\.tar\.gz")
    
    # 提取出所有备份文件的路径
    while IFS= read -r line; do
      if [[ "$line" =~ oss://.*/backup_([0-9]{8})[0-9]*\.tar\.gz ]]; then
        file_path=$(echo "$line" | awk '{print $NF}')
        backup_date="${BASH_REMATCH[1]}"
        
        if [ "$backup_date" -le "$keep_days_ago" ]; then
          echo "删除旧备份文件: $file_path"
          ossutil -c "/tmp/.ossutilconfig" rm "$file_path" --force
        fi
      fi
    done <<< "$backup_list"
  else
    # 列出所有备份文件
    backup_list=$(mc --config-dir "/tmp/.mc" ls "s3/$S3_BUCKET/$S3_PREFIX/" | grep -E "backup_[0-9]+\.tar\.gz")
    
    # 提取出所有备份文件的名称和日期
    while IFS= read -r line; do
      if [[ "$line" =~ [^/]*backup_([0-9]{8})[0-9]*\.tar\.gz ]]; then
        file_name=$(echo "$line" | grep -o "backup_[0-9]*.tar.gz")
        backup_date="${BASH_REMATCH[1]}"
        
        if [ "$backup_date" -le "$keep_days_ago" ]; then
          echo "删除旧备份文件: $file_name"
          mc --config-dir "/tmp/.mc" rm "s3/$S3_BUCKET/$S3_PREFIX/$file_name"
        fi
      fi
    done <<< "$backup_list"
  fi
}

# 主执行流程
main() {
  check_requirements
  perform_backup
  setup_auth
  upload_backup
  cleanup
  echo "备份完成！"
}

# 运行主函数
main
