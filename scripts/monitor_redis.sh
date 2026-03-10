#!/bin/bash

# Redis Monitoring Script
# Shows real-time Redis cache status for Quizify

echo "=================================="
echo "🔍 REDIS CACHE MONITOR - Quizify"
echo "=================================="
echo ""

# Detect Redis command (Docker or local)
if command -v redis-cli &> /dev/null; then
    REDIS_CMD="redis-cli"
elif docker ps --filter "name=redis" --format "{{.Names}}" 2>/dev/null | grep -q redis; then
    REDIS_CMD="docker exec -i quizify-redis redis-cli"
    echo "ℹ️  Using Redis in Docker container"
else
    echo "❌ Redis not found!"
    echo "Start with: docker-compose up -d redis"
    exit 1
fi

# Check if Redis is running
if ! $REDIS_CMD ping > /dev/null 2>&1; then
    echo "❌ Redis is not running!"
    echo "Start Redis with: docker-compose up -d redis"
    exit 1
fi

echo "✅ Redis is running"
echo ""

# Show Redis info
echo "📊 Redis Server Info:"
$REDIS_CMD INFO server | grep redis_version
$REDIS_CMD INFO server | grep uptime_in_seconds
echo ""

# Show total keys
echo "📦 Total Keys in Redis:"
$REDIS_CMD DBSIZE
echo ""

# Show cache keys by pattern
echo "🔑 Cache Keys by Type:"
echo ""

echo "1️⃣ User Tier Cache (user_tier:*):"
$REDIS_CMD --scan --pattern "user_tier:*" | wc -l | awk '{print "   Count: " $1 " keys"}'
$REDIS_CMD --scan --pattern "user_tier:*" | head -3 | while read key; do
    ttl=$($REDIS_CMD TTL "$key")
    echo "   • $key (TTL: ${ttl}s)"
done
echo ""

echo "2️⃣ Quiz Metadata Cache (quiz_metadata:*):"
$REDIS_CMD --scan --pattern "quiz_metadata:*" | wc -l | awk '{print "   Count: " $1 " keys"}'
$REDIS_CMD --scan --pattern "quiz_metadata:*" | head -3 | while read key; do
    ttl=$($REDIS_CMD TTL "$key")
    echo "   • $key (TTL: ${ttl}s)"
done
echo ""

echo "3️⃣ Browser Slot Management (browser:*):"
$REDIS_CMD --scan --pattern "browser:*" | wc -l | awk '{print "   Count: " $1 " keys"}'
$REDIS_CMD --scan --pattern "browser:*" | head -3 | while read key; do
    ttl=$($REDIS_CMD TTL "$key")
    value=$($REDIS_CMD GET "$key")
    echo "   • $key = $value (TTL: ${ttl}s)"
done
echo ""

# Show memory usage
echo "💾 Memory Usage:"
$REDIS_CMD INFO memory | grep used_memory_human
$REDIS_CMD INFO memory | grep used_memory_peak_human
echo ""

# Show stats
echo "📈 Command Stats:"
$REDIS_CMD INFO stats | grep total_commands_processed
$REDIS_CMD INFO stats | grep instantaneous_ops_per_sec
echo ""

echo "=================================="
echo "💡 Useful Commands:"
echo "=================================="
if [[ "$REDIS_CMD" == *"docker"* ]]; then
    echo "• Watch real-time: docker exec -it quizify-redis redis-cli MONITOR"
    echo "• List all keys:   docker exec -it quizify-redis redis-cli KEYS '*'"
    echo "• Clear cache:     docker exec -it quizify-redis redis-cli FLUSHDB"
else
    echo "• Watch real-time: redis-cli MONITOR"
    echo "• List all keys:   redis-cli KEYS '*'"
    echo "• Clear cache:     redis-cli FLUSHDB"
fi
echo "• Get a key:       redis-cli GET user_tier:YOUR_USER_ID"
echo ""

# Option to watch continuously
if [ "$1" == "watch" ]; then
    echo "👀 Watching Redis cache (press Ctrl+C to stop)..."
    echo ""
    watch -n 2 "redis-cli DBSIZE && echo '' && redis-cli --scan --pattern 'user_tier:*' | wc -l && redis-cli --scan --pattern 'quiz_metadata:*' | wc -l && redis-cli --scan --pattern 'browser:*' | wc -l"
fi
