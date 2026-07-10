param(
    [string]$BenchPath = "/home/administrator/frappe-bench",
    [string]$CivilSite = "fac.localhost",
    [int]$CivilPort = 8002
)

$command = @"
set -e
cd $BenchPath
redis-server config/redis_queue.conf --daemonize yes 2>/dev/null || true
redis-server config/redis_cache.conf --daemonize yes 2>/dev/null || true
nohup bench start > logs/agent-bench-start.log 2>&1 &
echo `$! > logs/agent-bench-start.pid
nohup bench --site $CivilSite serve --port $CivilPort > logs/civil-site-$CivilPort.log 2>&1 &
echo `$! > logs/civil-site-$CivilPort.pid
echo "bench pid: `$(cat logs/agent-bench-start.pid)"
echo "civil pid: `$(cat logs/civil-site-$CivilPort.pid)"
echo "log: $BenchPath/logs/agent-bench-start.log"
"@

wsl -e bash -lc ($command -replace "`r", "")
