#!/bin/sh
set -e

echo "=== [Job Agent Container Initializing on Coolify] ==="

# Export runtime environment variables to /etc/environment so Linux cron jobs have access
printenv | grep -v "no_proxy" >> /etc/environment || true

# Install cron schedule
crontab /app/crontab

# Ensure logs directory and log files exist
mkdir -p /app/logs /app/generated_cvs
touch /app/logs/discovery.log /app/logs/worker.log

# Start Linux cron service in background
cron

echo "✅ Cron daemon started successfully with Asia/Tokyo timezone."
echo "📋 Scheduled Jobs:"
echo "   - 06:00 JST: Daily Discovery Pipeline (run_daily_discovery.py)"
echo "   - 08:00 - 23:00 JST (Hourly): Precision Worker (run_queue_worker.py)"
echo "📡 Streaming logs to container stdout..."

# Tail logs so container stays running and outputs appear in Coolify UI
tail -F /app/logs/discovery.log /app/logs/worker.log
