#!/usr/bin/env bash
# 将最新日报复制到 reports/daily/YYYY/MM/ 并 commit
# 支持：基础日报 + yyPZ + 郑希研报 + 完整合编
set -euo pipefail

DATE=$(date +%F)
YEAR=$(date +%Y)
MONTH=$(date +%m)
TARGET_DIR="reports/daily/${YEAR}/${MONTH}"
mkdir -p "$TARGET_DIR"

# 要归档的报告类型
REPORTS=(
    "reports/report_${DATE}.md:report_${DATE}.md"
    "reports/yypz_${DATE}.md:yypz_${DATE}.md"
    "reports/zhengxi_${DATE}.md:zhengxi_${DATE}.md"
    "reports/full_${DATE}.md:full_${DATE}.md"
)

HAS_NEW=false
for ENTRY in "${REPORTS[@]}"; do
    SRC="${ENTRY%%:*}"
    DST="${ENTRY##*:}"
    if [ -f "$SRC" ]; then
        if [ ! -f "${TARGET_DIR}/${DST}" ] || ! cmp -s "$SRC" "${TARGET_DIR}/${DST}"; then
            cp "$SRC" "${TARGET_DIR}/${DST}"
            echo "✅ 已归档: $SRC"
            HAS_NEW=true
        else
            echo "⏭️ 无变化: $SRC"
        fi
    else
        echo "⚠️ 不存在: $SRC（跳过）"
    fi
done

if [ "$HAS_NEW" = false ]; then
    echo "⏭️ 无新内容，跳过提交"
    exit 0
fi

# 配置 git
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
