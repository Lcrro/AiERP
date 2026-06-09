param(
    [string]$BenchPath = "~/frappe-bench"
)

$command = @"
set -e
cd $BenchPath
redis-server config/redis_queue.conf --daemonize yes 2>/dev/null || true
redis-server config/redis_cache.conf --daemonize yes 2>/dev/null || true
nohup bench start > logs/agent-bench-start.log 2>&1 &
echo `$! > logs/agent-bench-start.pid
echo "bench pid: `$(cat logs/agent-bench-start.pid)"
echo "log: $BenchPath/logs/agent-bench-start.log"
"@

wsl -e bash -lc $command

