#!/bin/bash

# Docker Image Cleanup Script
# 删除指定 N 天之前的 Docker 镜像来节省空间
# 用法：./cleanup-docker-images.sh <image-name> <days>
#
# GitHub Actions Runner 兼容性说明:
# - 自托管 Runner 与 Docker 服务不会直接冲突
# - 脚本会跳过正在被容器使用的镜像
# - 建议将 Runner 使用的镜像加入排除列表
# - 避免在 Runner 执行任务时运行清理脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查参数
if [ $# -ne 2 ]; then
    echo -e "${RED}用法：$0 <image-name> <days>${NC}"
    echo "示例：$0 my-app 7  (删除 7 天前的镜像)"
    exit 1
fi

IMAGE_NAME="$1"
DAYS="$2"

# 排除列表 - 不会被删除的镜像（支持通配符）
EXCLUDED_IMAGES=(
    "ghcr.io/actions/"           # GitHub Actions 相关镜像
    "docker.io/actions/"         # Actions Runner 镜像
    "*runner*"                   # Runner 相关镜像
)

# 验证天数是数字
if ! [[ "$DAYS" =~ ^[0-9]+$ ]]; then
    echo -e "${RED}错误：天数必须是正整数${NC}"
    exit 1
fi

echo -e "${GREEN}开始清理 Docker 镜像...${NC}"
echo -e "镜像名称：${YELLOW}${IMAGE_NAME}${NC}"
echo -e "保留最近：${YELLOW}${DAYS}${NC} 天内的镜像"
echo ""

# 获取当前时间戳（秒）
CURRENT_TIME=$(date +%s)
SECONDS_IN_DAY=86400
CUTOFF_SECONDS=$((DAYS * SECONDS_IN_DAY))

# 计数器
DELETED_COUNT=0
KEPT_COUNT=0
TOTAL_SIZE_FREED=0

# 检查镜像是否在排除列表中
is_excluded() {
    local tags="$1"
    for pattern in "${EXCLUDED_IMAGES[@]}"; do
        if [[ "$tags" == *"$pattern"* ]]; then
            return 0
        fi
    done
    return 1
}

# 检查镜像是否正在被容器使用
is_in_use() {
    local image_id="$1"
    local containers=$(docker ps -q --filter "ancestor=$image_id" 2>/dev/null)
    if [ -n "$containers" ]; then
        return 0
    fi
    return 1
}

# 获取指定镜像的所有镜像 ID 和创建时间
# 使用 docker inspect 获取创建时间
while IFS= read -r IMAGE_ID; do
    if [ -z "$IMAGE_ID" ]; then
        continue
    fi
    
    # 获取镜像创建时间
    CREATED=$(docker inspect --format='{{.Created}}' "$IMAGE_ID" 2>/dev/null || echo "")
    if [ -z "$CREATED" ]; then
        continue
    fi
    
    # 转换创建时间为时间戳
    CREATED_TIMESTAMP=$(date -j -f "%Y-%m-%dT%H:%M:%S" "${CREATED%%.*}" +%s 2>/dev/null || date -d "$CREATED" +%s 2>/dev/null || echo "0")
    
    if [ "$CREATED_TIMESTAMP" -eq 0 ]; then
        echo -e "${YELLOW}跳过：无法解析镜像 $IMAGE_ID 的创建时间${NC}"
        continue
    fi
    
    # 计算镜像年龄（秒）
    AGE_SECONDS=$((CURRENT_TIME - CREATED_TIMESTAMP))
    AGE_DAYS=$((AGE_SECONDS / SECONDS_IN_DAY))
    
    # 获取镜像大小
    SIZE=$(docker inspect --format='{{.Size}}' "$IMAGE_ID" 2>/dev/null || echo "0")
    
    # 获取镜像标签用于检查
    TAGS=$(docker inspect --format='{{join .RepoTags ","}}' "$IMAGE_ID" 2>/dev/null || echo "<none>")
    
    if [ "$AGE_SECONDS" -gt "$CUTOFF_SECONDS" ]; then
        # 检查是否在排除列表中
        if is_excluded "$TAGS"; then
            echo -e "${GREEN}跳过 (排除列表)${NC} $TAGS"
            KEPT_COUNT=$((KEPT_COUNT + 1))
            continue
        fi
        
        # 检查是否正在被容器使用
        if is_in_use "$IMAGE_ID"; then
            echo -e "${GREEN}跳过 (正在使用)${NC} $TAGS"
            KEPT_COUNT=$((KEPT_COUNT + 1))
            continue
        fi
        
        # 镜像超过 N 天，删除
        echo -e "${YELLOW}删除${NC} [${AGE_DAYS}天前] $TAGS"
        
        # 强制删除镜像（不删除悬空镜像的依赖）
        if docker rmi -f "$IMAGE_ID" >/dev/null 2>&1; then
            DELETED_COUNT=$((DELETED_COUNT + 1))
            TOTAL_SIZE_FREED=$((TOTAL_SIZE_FREED + SIZE))
        else
            echo -e "${RED}失败：无法删除 $IMAGE_ID（可能正在被容器使用）${NC}"
        fi
    else
        # 保留镜像
        TAGS=$(docker inspect --format='{{join .RepoTags ","}}' "$IMAGE_ID" 2>/dev/null || echo "<none>")
        echo -e "${GREEN}保留${NC} [${AGE_DAYS}天前] $TAGS"
        KEPT_COUNT=$((KEPT_COUNT + 1))
    fi
done < <(docker images --format "{{.ID}}" "$IMAGE_NAME" 2>/dev/null || echo "")

# 转换字节到可读格式
if [ "$TOTAL_SIZE_FREED" -gt 1073741824 ]; then
    SIZE_HUMAN="$(echo "scale=2; $TOTAL_SIZE_FREED / 1073741824" | bc)GB"
elif [ "$TOTAL_SIZE_FREED" -gt 1048576 ]; then
    SIZE_HUMAN="$(echo "scale=2; $TOTAL_SIZE_FREED / 1048576" | bc)MB"
elif [ "$TOTAL_SIZE_FREED" -gt 1024 ]; then
    SIZE_HUMAN="$(echo "scale=2; $TOTAL_SIZE_FREED / 1024" | bc)KB"
else
    SIZE_HUMAN="${TOTAL_SIZE_FREED}B"
fi

echo ""
echo -e "${GREEN}=== 清理完成 ===${NC}"
echo -e "删除镜像数：${RED}${DELETED_COUNT}${NC}"
echo -e "保留镜像数：${GREEN}${KEPT_COUNT}${NC}"
echo -e "释放空间：${GREEN}${SIZE_HUMAN}${NC}"

# 清理悬空镜像（可选）
read -p "是否同时清理悬空镜像 (dangling images)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}清理悬空镜像...${NC}"
    docker images -f "dangling=true" -q | xargs -r docker rmi -f
    echo -e "${GREEN}悬空镜像清理完成${NC}"
fi