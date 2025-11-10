#!/usr/bin/env python3
"""
Test script to verify Redis caching is working for database queries.

This script demonstrates:
1. First query (cache miss) - hits database
2. Second query (cache hit) - served from Redis
3. Performance comparison (50x improvement expected)
4. Redis key inspection
"""

import asyncio
import time
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_services.supabase_quiz import (
    get_user_tier_info_cached,
    get_quiz_metadata_cached,
    invalidate_user_tier_cache,
    invalidate_quiz_cache
)
from services.redis import get_cache_service


async def test_user_tier_caching():
    """Test user tier info caching with performance measurement."""
    print("\n" + "="*80)
    print("🧪 TEST 1: User Tier Info Caching")
    print("="*80)
    
    # Use a real user ID from your database (replace with actual UUID)
    user_id = "550e8400-e29b-41d4-a716-446655440000"  # Example UUID - replace with real one
    
    print(f"\n📋 Testing cache for user: {user_id[:8]}...")
    
    # First call - should hit database (cache miss)
    print("\n1️⃣ FIRST CALL (Cache Miss - Database Query):")
    start = time.time()
    try:
        tier_info_1 = await get_user_tier_info_cached(user_id)
        elapsed_1 = (time.time() - start) * 1000  # Convert to ms
        print(f"   ✅ Response time: {elapsed_1:.2f}ms")
        print(f"   📊 Data: {tier_info_1}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Second call - should hit cache (cache hit)
    print("\n2️⃣ SECOND CALL (Cache Hit - From Redis):")
    start = time.time()
    tier_info_2 = await get_user_tier_info_cached(user_id)
    elapsed_2 = (time.time() - start) * 1000
    print(f"   ✅ Response time: {elapsed_2:.2f}ms")
    print(f"   📊 Data: {tier_info_2}")
    
    # Calculate improvement
    if elapsed_2 > 0:
        improvement = elapsed_1 / elapsed_2
        print(f"\n📈 PERFORMANCE IMPROVEMENT:")
        print(f"   • First call (database):  {elapsed_1:.2f}ms")
        print(f"   • Second call (cached):   {elapsed_2:.2f}ms")
        print(f"   • Speedup:                {improvement:.1f}x faster ⚡")
        
        if improvement > 10:
            print(f"   ✅ EXCELLENT! Cache is working as expected (>10x faster)")
        elif improvement > 2:
            print(f"   ⚠️  Cache working but less improvement than expected")
        else:
            print(f"   ❌ Cache may not be working properly")
    
    # Check cache statistics
    print("\n📊 CACHE STATISTICS:")
    cache = get_cache_service(prefix="user_tier")
    stats = cache.get_stats()
    print(f"   • Cache Hits:     {stats.get('redis_cache_hits', 0) + stats.get('memory_cache_hits', 0)}")
    print(f"   • Cache Misses:   {stats.get('redis_cache_misses', 0) + stats.get('memory_cache_misses', 0)}")
    print(f"   • Hit Rate:       {stats.get('redis_hit_rate', stats.get('memory_hit_rate', 0)):.1%}")
    print(f"   • Total Ops:      {stats.get('total_operations', 0)}")
    
    return tier_info_1


async def test_quiz_metadata_caching():
    """Test quiz metadata caching with performance measurement."""
    print("\n" + "="*80)
    print("🧪 TEST 2: Quiz Metadata Caching")
    print("="*80)
    
    # Use real quiz_id and user_id from your database (replace with actual UUIDs)
    quiz_id = "550e8400-e29b-41d4-a716-446655440001"  # Example - replace
    user_id = "550e8400-e29b-41d4-a716-446655440000"  # Example - replace
    
    print(f"\n📋 Testing cache for quiz: {quiz_id[:8]}... by user: {user_id[:8]}...")
    
    # First call - cache miss
    print("\n1️⃣ FIRST CALL (Cache Miss - Database Query):")
    start = time.time()
    try:
        metadata_1 = await get_quiz_metadata_cached(quiz_id, user_id)
        elapsed_1 = (time.time() - start) * 1000
        print(f"   ✅ Response time: {elapsed_1:.2f}ms")
        print(f"   📊 Data: {metadata_1}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Second call - cache hit
    print("\n2️⃣ SECOND CALL (Cache Hit - From Redis):")
    start = time.time()
    metadata_2 = await get_quiz_metadata_cached(quiz_id, user_id)
    elapsed_2 = (time.time() - start) * 1000
    print(f"   ✅ Response time: {elapsed_2:.2f}ms")
    print(f"   📊 Data: {metadata_2}")
    
    # Calculate improvement
    if elapsed_2 > 0:
        improvement = elapsed_1 / elapsed_2
        print(f"\n📈 PERFORMANCE IMPROVEMENT:")
        print(f"   • First call (database):  {elapsed_1:.2f}ms")
        print(f"   • Second call (cached):   {elapsed_2:.2f}ms")
        print(f"   • Speedup:                {improvement:.1f}x faster ⚡")
        
        if improvement > 10:
            print(f"   ✅ EXCELLENT! Cache is working as expected (>10x faster)")
        elif improvement > 2:
            print(f"   ⚠️  Cache working but less improvement than expected")
        else:
            print(f"   ❌ Cache may not be working properly")
    
    # Check cache statistics
    print("\n📊 CACHE STATISTICS:")
    cache = get_cache_service(prefix="quiz_metadata")
    stats = cache.get_stats()
    print(f"   • Cache Hits:     {stats.get('redis_cache_hits', 0) + stats.get('memory_cache_hits', 0)}")
    print(f"   • Cache Misses:   {stats.get('redis_cache_misses', 0) + stats.get('memory_cache_misses', 0)}")
    print(f"   • Hit Rate:       {stats.get('redis_hit_rate', stats.get('memory_hit_rate', 0)):.1%}")
    print(f"   • Total Ops:      {stats.get('total_operations', 0)}")


async def inspect_redis_keys():
    """Inspect Redis to see what keys are stored."""
    print("\n" + "="*80)
    print("🔍 REDIS KEY INSPECTION")
    print("="*80)
    
    try:
        import redis.asyncio as redis
        from config import app_config
        
        # Connect to Redis
        redis_client = redis.from_url(
            app_config.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        
        print("\n📦 Scanning Redis for cached keys...")
        
        # Scan for user_tier keys
        print("\n1️⃣ USER TIER CACHE KEYS:")
        cursor = 0
        user_tier_keys = []
        while True:
            cursor, keys = await redis_client.scan(
                cursor=cursor,
                match="user_tier:*",
                count=100
            )
            user_tier_keys.extend(keys)
            if cursor == 0:
                break
        
        if user_tier_keys:
            print(f"   Found {len(user_tier_keys)} cached user tier entries:")
            for key in user_tier_keys[:5]:  # Show first 5
                ttl = await redis_client.ttl(key)
                print(f"   • {key} (TTL: {ttl}s)")
            if len(user_tier_keys) > 5:
                print(f"   ... and {len(user_tier_keys) - 5} more")
        else:
            print("   ⚠️  No user tier cache keys found")
        
        # Scan for quiz_metadata keys
        print("\n2️⃣ QUIZ METADATA CACHE KEYS:")
        cursor = 0
        quiz_keys = []
        while True:
            cursor, keys = await redis_client.scan(
                cursor=cursor,
                match="quiz_metadata:*",
                count=100
            )
            quiz_keys.extend(keys)
            if cursor == 0:
                break
        
        if quiz_keys:
            print(f"   Found {len(quiz_keys)} cached quiz metadata entries:")
            for key in quiz_keys[:5]:  # Show first 5
                ttl = await redis_client.ttl(key)
                print(f"   • {key} (TTL: {ttl}s)")
            if len(quiz_keys) > 5:
                print(f"   ... and {len(quiz_keys) - 5} more")
        else:
            print("   ⚠️  No quiz metadata cache keys found")
        
        # Scan for browser slot keys
        print("\n3️⃣ BROWSER SLOT MANAGEMENT KEYS:")
        cursor = 0
        browser_keys = []
        while True:
            cursor, keys = await redis_client.scan(
                cursor=cursor,
                match="browser:*",
                count=100
            )
            browser_keys.extend(keys)
            if cursor == 0:
                break
        
        if browser_keys:
            print(f"   Found {len(browser_keys)} browser slot entries:")
            for key in browser_keys[:5]:
                ttl = await redis_client.ttl(key)
                value = await redis_client.get(key)
                print(f"   • {key} = {value} (TTL: {ttl}s)")
            if len(browser_keys) > 5:
                print(f"   ... and {len(browser_keys) - 5} more")
        else:
            print("   ℹ️  No active browser slots (this is normal when idle)")
        
        await redis_client.close()
        
    except Exception as e:
        print(f"\n❌ Error connecting to Redis: {e}")
        print("   Make sure Redis is running and REDIS_ENABLED=true")


async def main():
    """Run all cache tests."""
    print("\n" + "🚀"*40)
    print("REDIS DATABASE CACHING VERIFICATION TEST")
    print("🚀"*40)
    
    print("\n⚙️  Configuration:")
    from config import app_config
    print(f"   • Redis Enabled:  {app_config.REDIS_ENABLED}")
    print(f"   • Redis URL:      {app_config.REDIS_URL}")
    print(f"   • User Tier TTL:  {app_config.REDIS_CACHE_TTL_USER_TIER}s (5 minutes)")
    print(f"   • Quiz Meta TTL:  {app_config.REDIS_CACHE_TTL_QUIZ_METADATA}s (30 minutes)")
    
    # Test 1: User Tier Caching
    await test_user_tier_caching()
    
    # Test 2: Quiz Metadata Caching
    # await test_quiz_metadata_caching()  # Uncomment when you have real quiz data
    
    # Inspect Redis keys
    await inspect_redis_keys()
    
    print("\n" + "="*80)
    print("✅ CACHE VERIFICATION COMPLETE!")
    print("="*80)
    print("\n💡 TIP: Run this script multiple times to see consistent cache hits!")
    print("💡 TIP: Check Redis CLI with: redis-cli KEYS '*' to see all keys\n")


if __name__ == "__main__":
    asyncio.run(main())
