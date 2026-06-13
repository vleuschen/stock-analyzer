#!/usr/bin/env bash
# 将最新日报复制到 reports/daily/YYYY/MM/ 并 commit
set -euo pipefail

DATE=$(date +%F)
YEAR=$(date +%Y)
MONTH=$(date +%m)
SOURCE="reports/report_${DATE}.md"
TARGET_DIR="reports/daily/${YEAR}/${MONTH}"
TARGET="${TARGET_DIR}/report_${DATE}.md"

# 检查源文件是否存在
if [ ! -f "$SOURCE" ]; then
    echo "⚠️ 日报文件不存在: $SOURCE，跳过归档"
    exit 0
fi

# 创建目标目录
mkdir -p "$TARGET_DIR"

# 复制文件（如果内容不同）
if [ -f "$TARGET" ] && cmp -s "$SOURCE" "$TARGET"; then
    echo "⏭️ 日报 $DATE 已归档且无变化，跳过"
    exit 0
fi

cp "$SOURCE" "$TARGET"
echo "✅ 已归档: $SOURCE → $TARGET"

# 配置 git（GitHub Actions 环境需要）
git config user.name "stock-analyzer[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

# commit + push
git add "reports/daily/${YEAR}/${MONTH}/"
if git diff --quiet && git diff --staged --quiet; then
    echo "⏭️ 无新内容可提交"
else
    git commit -m "📁 归档日报 ${DATE}"
    git push
    echo "✅ 已推送到仓库"
fi
