.PHONY: analyze archive weekly push-test

# 运行每日分析（本地）
analyze:
	python analyzer.py

# 归档最新日报到 reports/daily/YYYY/MM/
archive:
	bash scripts/archive_report.sh

# 生成本周复盘总结
weekly:
	python scripts/weekly_review.py

# 发送测试推送
push-test:
	python -c "from notifier import push_test; import os; push_test(os.getenv('SERVERCHAN_SENDKEY', ''))"
