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
BACKUP_ID="" # 备份ID，如不提供则使用最新备份

# 恢复目录和临时目录
RESTORE_DIR="/app/restore"
TEMP_DIR="/tmp/mysql_backup"

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
[ -n "$S3_TYPE" ] && S3_TYPE="$S3_TYPE"
[ -n "$BACKUP_ID" ] && BACKUP_ID="$BACKUP_ID"


# 判断是否为阿里云OSS
if [[ "$S3_ENDPOINT" == *"aliyuncs"* ]]; then
  S3_TYPE="aliyun"
fi


# 解析命令行参数
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-id)
      BACKUP_ID="$2"
      shift 2
      ;;
    *)
      echo "未知选项: $1"
      exit 1
      ;;
  esac
done

# 检查必需的变量
if [ -z "$S3_BUCKET" ] || [ -z "$S3_ACCESS_KEY" ] || [ -z "$S3_SECRET_KEY" ]; then
  echo "错误: S3_BUCKET, S3_ACCESS_KEY, 和 S3_SECRET_KEY 必须设置。"
  exit 1
fi

# 创建必要的目录
mkdir -p "$RESTORE_DIR"
mkdir -p "$TEMP_DIR"

# 配置认证和工具函数
setup_auth() {
  if [[ "$S3_TYPE" == "aliyun" ]]; then
    echo "配置 ossutil..."
    config_file="/tmp/.ossutilconfig"
    cat > "$config_file" << EOF
[Credentials]
language=EN
endpoint=$S3_ENDPOINT
accessKeyID=$S3_ACCESS_KEY
accessKeySecret=$S3_SECRET_KEY
EOF
  else
    echo "配置 MinIO 客户端..."
    mkdir -p "/tmp/.mc"
    mc --config-dir "/tmp/.mc" alias set s3 "$S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY"
  fi
}
# 列出备份并获取目标备份文件名
get_backup_file() {
  local backup_files=""
  local target_file=""
  
  # 如果指定了备份ID，直接返回对应文件名
  if [ -n "$BACKUP_ID" ]; then
    target_file="backup_${BACKUP_ID}.tar.gz"
    if [ -n "$S3_PREFIX" ]; then
      target_file="$S3_PREFIX/$target_file"
    fi
    echo "使用指定备份: $target_file" >&2
    echo "$target_file"
    return
  fi
  
  # 否则查找最新的备份文件
  echo "查找最新备份..." >&2
  
  if [[ "$S3_TYPE" == "aliyun" ]]; then
    # 阿里云OSS方式
    echo "列出 OSS 存储桶中的备份..." >&2
    backup_files=$(ossutil -c "/tmp/.ossutilconfig" ls "oss://$S3_BUCKET/$S3_PREFIX/" | grep -E "backup_[0-9]+\.tar\.gz")
    
    if [ -z "$backup_files" ]; then
      echo "没有找到备份文件" >&2
      exit 1
    fi
    
    # 提取所有备份文件名并按时间戳排序（最新的在前）
    all_backups=$(echo "$backup_files" | grep -o "backup_[0-9]*\.tar\.gz" | sort -r)
    target_file=$(echo "$all_backups" | head -n 1)
  else
    # MinIO/S3方式
    echo "列出 S3 存储桶中的备份..." >&2
    mc --config-dir "/tmp/.mc" ls "s3/$S3_BUCKET/$S3_PREFIX/" >&2
    
    # 提取所有备份文件并按名称排序（最新的在前）
    all_backups=$(mc --config-dir "/tmp/.mc" ls "s3/$S3_BUCKET/$S3_PREFIX/" | grep -o "backup_[0-9]*\.tar\.gz" | sort -r)
    
    if [ -z "$all_backups" ]; then
      echo "没有找到备份文件" >&2
      exit 1
    fi
    
    target_file=$(echo "$all_backups" | head -n 1)
  fi
  
  if [ -z "$target_file" ]; then
    echo "错误: 无法找到有效的备份文件" >&2
    exit 1
  fi
  
  # 添加前缀（如果需要）
  if [ -n "$S3_PREFIX" ]; then
    full_path="$S3_PREFIX/$target_file"
  else
    full_path="$target_file"
  fi
  
  echo "找到最新备份: $full_path" >&2
  echo "$full_path"
}

# 下载备份文件
download_backup() {
  local backup_file="$1"
  local success=false
  
  echo "下载备份文件: $backup_file"
  
  if [[ "$S3_TYPE" == "aliyun" ]]; then
    echo "使用 ossutil 下载..."
    ossutil -c "/tmp/.ossutilconfig" cp "oss://$S3_BUCKET/$backup_file" "$TEMP_DIR/" --checkpoint-dir="/tmp/.ossutil_checkpoint" --force
    if [ $? -eq 0 ]; then
      success=true
    fi
  else
    echo "使用 MinIO 客户端下载..."
    mc --config-dir "/tmp/.mc" cp "s3/$S3_BUCKET/$backup_file" "$TEMP_DIR/"
    if [ $? -eq 0 ]; then
      success=true
    fi
  fi
  
  if [ "$success" = false ]; then
    echo "下载失败"
    exit 1
  fi
  
  echo "下载完成: $TEMP_DIR/$(basename "$backup_file")"
}

# 解压备份并恢复
restore_backup() {
  local backup_file=$(basename "$1")
  
  echo "解压备份文件..."
  tar xzf "$TEMP_DIR/$backup_file" -C "$TEMP_DIR"
  if [ $? -ne 0 ]; then
    echo "解压失败"
    exit 1
  fi
  
  # 获取解压后的目录名
  backup_dir="${backup_file%.tar.gz}"
  
  if [ ! -d "$TEMP_DIR/$backup_dir" ]; then
    echo "错误: 无法找到解压后的目录: $TEMP_DIR/$backup_dir"
    exit 1
  fi
  
  echo "将文件复制到恢复目录: $RESTORE_DIR"
  cp -r "$TEMP_DIR/$backup_dir"/* "$RESTORE_DIR/"
  if [ $? -ne 0 ]; then
    echo "恢复失败"
    exit 1
  fi
  
  # 设置权限
  echo "设置权限..."
  chown -R mysql:mysql "$RESTORE_DIR" 2>/dev/null || echo "警告: 无法更改所有权为mysql用户，如果在容器内运行这可能是正常的。"
  chmod -R 750 "$RESTORE_DIR"
  
  echo "清理临时文件..."
  rm -rf "$TEMP_DIR/$backup_dir" "$TEMP_DIR/$backup_file"
  
  echo "恢复完成到: $RESTORE_DIR"
  echo "注意: 您可能需要重启MySQL服务器以使用恢复的数据。"
}

# 主执行流程
main() {
  setup_auth
  backup_file=$(get_backup_file)
  download_backup "$backup_file"
  restore_backup "$backup_file"
}

# 运行主函数
main
