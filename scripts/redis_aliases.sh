#!/bin/bash

# Redis Aliases for Docker - Quizify
# 
# Usage:
#   source scripts/redis_aliases.sh
# Or add to ~/.zshrc:
#   echo "source $PWD/scripts/redis_aliases.sh" >> ~/.zshrc
#   source ~/.zshrc

# Core Redis commands
alias redis-cli='docker exec -it quizify-redis redis-cli'
alias redis-ping='docker exec -it quizify-redis redis-cli ping'

# Monitoring
alias redis-monitor='docker exec -it quizify-redis redis-cli MONITOR'
alias redis-info='docker exec -it quizify-redis redis-cli INFO'

# Key operations
alias redis-keys='docker exec -it quizify-redis redis-cli KEYS "*"'
alias redis-scan='docker exec -it quizify-redis redis-cli --scan'
alias redis-dbsize='docker exec -it quizify-redis redis-cli DBSIZE'

# Cache management
alias redis-clear='docker exec -it quizify-redis redis-cli FLUSHDB'
alias redis-clearall='docker exec -it quizify-redis redis-cli FLUSHALL'

# Cache inspection
alias redis-user-cache='docker exec -it quizify-redis redis-cli KEYS "user_tier:*"'
alias redis-quiz-cache='docker exec -it quizify-redis redis-cli KEYS "quiz_metadata:*"'
alias redis-browser-slots='docker exec -it quizify-redis redis-cli KEYS "browser:*"'

# Stats
alias redis-stats='docker exec -it quizify-redis redis-cli INFO stats'
alias redis-memory='docker exec -it quizify-redis redis-cli INFO memory'

# Docker management
alias redis-logs='docker logs quizify-redis -f'
alias redis-restart='docker-compose restart redis'
alias redis-stop='docker-compose stop redis'
alias redis-start='docker-compose up -d redis'

echo "✅ Redis Docker aliases loaded!"
echo ""
echo "Try these commands:"
echo "  redis-ping          # Test connection"
echo "  redis-keys          # See all cache keys"
echo "  redis-monitor       # Watch real-time activity"
echo "  redis-dbsize        # Total keys count"
echo "  redis-user-cache    # User tier cache keys"
echo "  redis-clear         # Clear all cache"
echo ""
