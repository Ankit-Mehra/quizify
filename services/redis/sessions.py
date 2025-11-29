"""
Session Management Service for Quizify

Provides distributed session management using Redis for:
- Multi-device authentication tracking
- Session validation and refresh
- Logout single/all devices
- Session activity monitoring

Architecture:
- Redis Hash: session:{session_id} → session metadata
- Redis Set: user_sessions:{user_id} → set of session_ids
- 24-hour TTL per session (auto-cleanup)
"""

import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime
from typing import List, Optional

import redis.asyncio as redis
from pydantic import BaseModel, Field

from config import Config

logger = logging.getLogger(__name__)


class SessionInfo(BaseModel):
    """Session metadata stored in Redis"""

    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="User who owns this session")
    created_at: datetime = Field(..., description="Session creation timestamp")
    last_active: datetime = Field(..., description="Last activity timestamp")
    device_type: str = Field(..., description="Device type: browser, mobile, api")
    ip_address: str = Field(..., description="Hashed IP address")
    user_agent: str = Field(..., description="User agent string (truncated)")
    refresh_token_hash: Optional[str] = Field(None, description="HMAC hash of refresh token (for cookie-based lookup)")
    client_session_token: Optional[str] = Field(None, description="Optional HMAC-signed token for UI identification only")

    @property
    def is_expired(self) -> bool:
        """Check if session has exceeded configured TTL"""
        age = datetime.utcnow() - self.last_active
        return age.total_seconds() > Config.REDIS_SESSION_TTL


class SessionError(Exception):
    """Base exception for session operations"""

    pass


class SessionNotFoundError(SessionError):
    """Raised when session doesn't exist"""

    pass


class SessionExpiredError(SessionError):
    """Raised when session has expired"""

    pass


class TooManySessionsError(SessionError):
    """Raised when user has too many active sessions"""

    def __init__(self, user_id: str, count: int, max_sessions: int = None):
        self.user_id = user_id
        self.count = count
        self.max_sessions = max_sessions or Config.MAX_SESSIONS_PER_USER
        super().__init__(
            f"User {user_id} has {count} active sessions (max: {self.max_sessions})"
        )


class SessionService:
    """
    Manages user authentication sessions using Redis.

    Provides multi-device session tracking, logout-all-devices,
    and session activity monitoring. Sessions expire after 30 days
    of inactivity (aligned with refresh token expiry).

    Redis Data Structure:
    - session:{session_id} → Hash with session metadata
    - user_sessions:{user_id} → Set of active session_ids

    Example:
        >>> service = SessionService(redis_client)
        >>> session_id = await service.create_session("user_123", "browser")
        >>> session_info = await service.validate_session(session_id)
        >>> await service.refresh_session(session_id)
        >>> await service.logout(session_id)
    """

    # Lua script for atomic session limit check + add
    # Returns: 1 if added successfully, 0 if limit exceeded
    CREATE_SESSION_SCRIPT = """
    local user_sessions_key = KEYS[1]
    local session_id = ARGV[1]
    local max_sessions = tonumber(ARGV[2])
    
    local count = redis.call('SCARD', user_sessions_key)
    if count >= max_sessions then
        return 0
    end
    
    redis.call('SADD', user_sessions_key, session_id)
    return 1
    """
    
    # Module-level flag to log IP_HASH_SECRET warning only once
    _ip_hash_warning_logged = False

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize session service.

        Args:
            redis_client: Async Redis client instance
        """
        self.redis = redis_client
        self.session_ttl = Config.REDIS_SESSION_TTL
        self.MAX_SESSIONS_PER_USER = Config.MAX_SESSIONS_PER_USER

    @staticmethod
    def _hash_ip(ip_address: str) -> str:
        """
        Hash IP address with secret salt for privacy.
        
        Uses HMAC-SHA256 with secret salt to prevent rainbow table attacks.
        If IP_HASH_SECRET is not set, stores "redacted" instead of exposing
        the IP in any form.
        
        Args:
            ip_address: Raw IP address
            
        Returns:
            Salted hash or "redacted" if no secret configured
        """
        # Get secret salt from environment (should be set in production)
        secret = os.getenv("IP_HASH_SECRET")
        if not secret:
            # Log warning only once to avoid flooding logs
            if not SessionService._ip_hash_warning_logged:
                logger.warning("IP_HASH_SECRET not set - IP addresses will not be stored (logged once)")
                SessionService._ip_hash_warning_logged = True
            return "redacted"
        
        # Use HMAC for salted hashing (prevents rainbow table attacks)
        h = hmac.new(secret.encode(), ip_address.encode(), hashlib.sha256)
        return h.hexdigest()[:16]

    @staticmethod
    def _truncate_user_agent(user_agent: str, max_length: int = 100) -> str:
        """Truncate user agent to prevent excessive memory usage"""
        if len(user_agent) > max_length:
            return user_agent[:max_length] + "..."
        return user_agent

    @staticmethod
    def _generate_session_id() -> str:
        """Generate cryptographically secure session ID"""
        return f"sess_{uuid.uuid4()}"
    
    @staticmethod
    def _hash_refresh_token(refresh_token: str) -> str:
        """
        Create HMAC hash of refresh token for cookie-based session lookup.
        
        Uses IP_HASH_SECRET to create a one-way hash that can be stored in 
        Redis to map refresh tokens to sessions. Fails hard if secret not set.
        
        Args:
            refresh_token: The JWT refresh token from Supabase
            
        Returns:
            HMAC-SHA256 hash of the token (first 32 chars for efficiency)
            
        Raises:
            RuntimeError: If IP_HASH_SECRET environment variable is not set
        """
        secret = os.getenv("IP_HASH_SECRET")
        if not secret:
            raise RuntimeError(
                "IP_HASH_SECRET environment variable must be set for secure session token generation. "
                "Application cannot start without this security requirement."
            )
        h = hmac.new(secret.encode(), refresh_token.encode(), hashlib.sha256)
        return h.hexdigest()[:32]
    
    @staticmethod
    def _generate_client_session_token(session_id: str, user_id: str) -> str:
        """
        Generate HMAC-signed client session token for UI purposes only.
        
        This token is NOT used for authentication - it's purely for frontend
        to identify which device is "current" in the session list UI without
        storing the real session_id in localStorage (XSS protection).
        
        Args:
            session_id: The real server-side session identifier
            user_id: User who owns the session
            
        Returns:
            HMAC-signed token that frontend can safely store
            
        Raises:
            RuntimeError: If IP_HASH_SECRET environment variable is not set
        """
        secret = os.getenv("IP_HASH_SECRET")
        if not secret:
            raise RuntimeError(
                "IP_HASH_SECRET environment variable must be set for secure session token generation. "
                "Application cannot start without this security requirement."
            )
        # Combine session_id + user_id for uniqueness, then sign with HMAC
        payload = f"{session_id}:{user_id}"
        signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        # Return a compact token: first 8 chars of session_id + signature
        return f"cst_{session_id[:8]}_{signature}"

    async def create_session(
        self,
        user_id: str,
        device_type: str = "browser",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        refresh_token: Optional[str] = None,
    ) -> str:
        """
        Create a new authentication session atomically.

        Generates a unique session ID, stores session metadata in Redis,
        and adds session to user's active session set. Uses Lua script
        to ensure atomic check-and-add operation (prevents race conditions).
        
        Creates a refresh_token → session_id mapping to enable cookie-based 
        session lookup (XSS-safe authentication).

        Args:
            user_id: User identifier
            device_type: Type of device ('browser', 'mobile', 'api')
            ip_address: Client IP address (will be hashed with secret salt)
            user_agent: Client user agent string (will be truncated)
            refresh_token: Supabase refresh token for cookie-based lookup (required)

        Returns:
            str: client_session_token - HMAC-signed token for UI identification only

        Raises:
            TooManySessionsError: If user has >= MAX_SESSIONS_PER_USER active sessions
            redis.RedisError: If Redis operation fails

        Example:
            >>> client_token = await service.create_session(
            ...     user_id="user_123",
            ...     device_type="browser",
            ...     ip_address="192.168.1.1",
            ...     user_agent="Mozilla/5.0...",
            ...     refresh_token="eyJhbGc..."
            ... )
        """
        try:
            user_sessions_key = f"user_sessions:{user_id}"
            session_id = self._generate_session_id()
            
            # IMPORTANT: Cleanup stale session references before checking limits
            # This removes session IDs from the set that point to expired/deleted sessions
            # Without this, logout-without-session-id would leave orphan references
            await self.cleanup_expired_sessions(user_id)
            
            # Atomic check-and-add using Lua script (prevents race conditions)
            try:
                result = await self.redis.eval(
                    self.CREATE_SESSION_SCRIPT,
                    1,  # number of keys
                    user_sessions_key,  # KEYS[1]
                    session_id,  # ARGV[1]
                    str(self.MAX_SESSIONS_PER_USER),  # ARGV[2]
                )
            except Exception as lua_error:
                # SECURITY: Only allow non-atomic fallback in test environments
                # Production Redis MUST support Lua scripts for atomic session creation
                is_fakeredis = hasattr(self.redis, '__class__') and 'fakeredis' in str(self.redis.__class__.__module__).lower()
                is_testing = Config.is_testing()  # Use official testing flag
                
                # Very strict fallback detection - must be fakeredis AND testing mode
                if is_fakeredis and is_testing and "unknown command" in str(lua_error).lower():
                    logger.error(
                        f"TESTING MODE: Using non-atomic session creation fallback. "
                        f"This is ONLY acceptable in tests. Error: {lua_error}"
                    )
                    # Non-atomic fallback (race condition possible, but acceptable in tests)
                    session_count = await self.redis.scard(user_sessions_key)
                    if session_count >= self.MAX_SESSIONS_PER_USER:
                        result = 0
                    else:
                        await self.redis.sadd(user_sessions_key, session_id)
                        result = 1
                else:
                    # Production: Fail hard if Lua not supported
                    logger.error(
                        f"CRITICAL: Lua script failed in production. This breaks atomic session creation. "
                        f"Error: {lua_error}"
                    )
                    raise
            
            if result == 0:
                # Limit exceeded - get current count for error message
                session_count = await self.redis.scard(user_sessions_key)
                logger.warning(
                    f"User {user_id[:8]}... has too many sessions: {session_count}"
                )
                raise TooManySessionsError(
                    user_id, session_count, max_sessions=self.MAX_SESSIONS_PER_USER
                )

            # Prepare session metadata
            now = datetime.utcnow()
            hashed_ip = self._hash_ip(ip_address) if ip_address else "unknown"
            truncated_ua = (
                self._truncate_user_agent(user_agent) if user_agent else "unknown"
            )
            
            # Generate client session token for UI purposes (XSS-safe)
            client_session_token = self._generate_client_session_token(session_id, user_id)
            
            # Hash refresh token if provided (for cookie-based session lookup)
            refresh_token_hash = None
            if refresh_token:
                refresh_token_hash = self._hash_refresh_token(refresh_token)

            session_data = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": now.isoformat(),
                "last_active": now.isoformat(),
                "device_type": device_type,
                "ip_address": hashed_ip,
                "user_agent": truncated_ua,
                "client_session_token": client_session_token,
            }
            
            # Add refresh_token_hash if provided
            if refresh_token_hash:
                session_data["refresh_token_hash"] = refresh_token_hash

            # Store session in Redis hash
            session_key = f"session:{session_id}"
            await self.redis.hset(session_key, mapping=session_data)
            await self.redis.expire(session_key, self.session_ttl)

            # Set TTL on user sessions set
            await self.redis.expire(user_sessions_key, self.session_ttl)
            
            # Create reverse mapping for cookie-based lookup
            if refresh_token_hash:
                refresh_token_key = f"refresh_token:{refresh_token_hash}"
                await self.redis.set(refresh_token_key, session_id, ex=self.session_ttl)
                logger.info(
                    f"Created session for user {user_id[:8]}... on {device_type} device (cookie-based)"
                )
            
            # Create reverse mapping for client token (O(1) lookup)
            client_token_key = f"client_token:{client_session_token}"
            await self.redis.set(client_token_key, session_id, ex=self.session_ttl)

            return client_session_token

        except TooManySessionsError:
            raise
        except Exception as e:
            logger.error(f"Failed to create session for user {user_id[:8]}...: {e}")
            raise

    async def validate_session(self, session_id: str) -> Optional[SessionInfo]:
        """
        Validate a session and return its metadata.

        Args:
            session_id: Session identifier to validate

        Returns:
            SessionInfo if valid, None if session doesn't exist or expired

        Example:
            >>> session_info = await service.validate_session(session_id)
            >>> if session_info:
            ...     print(f"User: {session_info.user_id}")
        """
        try:
            session_key = f"session:{session_id}"
            session_data = await self.redis.hgetall(session_key)

            if not session_data:
                return None

            # Convert bytes to strings if needed
            if isinstance(next(iter(session_data.keys())), bytes):
                session_data = {
                    k.decode(): v.decode() if isinstance(v, bytes) else v 
                    for k, v in session_data.items()
                }

            # Parse datetime fields
            session_data["created_at"] = datetime.fromisoformat(
                session_data["created_at"]
            )
            session_data["last_active"] = datetime.fromisoformat(
                session_data["last_active"]
            )
            
            # Handle optional fields (may not exist in older sessions)
            if "refresh_token_hash" not in session_data:
                session_data["refresh_token_hash"] = None
            if "client_session_token" not in session_data:
                session_data["client_session_token"] = None

            session_info = SessionInfo(**session_data)

            # Check if expired
            if session_info.is_expired:
                logger.info(f"Session {session_id[:12]}... has expired")
                await self.logout(session_id)
                return None

            return session_info

        except Exception as e:
            logger.error(f"Failed to validate session {session_id[:12]}...: {e}")
            return None

    async def find_session_by_refresh_token(self, refresh_token: str) -> Optional[str]:
        """
        Find session ID by refresh token (cookie-based lookup).
        
        This enables pure cookie-based authentication without requiring
        the X-Session-ID header. The frontend never stores session_id,
        eliminating XSS session replay risk.
        
        Args:
            refresh_token: The JWT refresh token from httpOnly cookie
            
        Returns:
            session_id if found, None otherwise
            
        Example:
            >>> session_id = await service.find_session_by_refresh_token(refresh_token)
            >>> if session_id:
            ...     session_info = await service.validate_session(session_id)
        """
        try:
            refresh_token_hash = self._hash_refresh_token(refresh_token)
            refresh_token_key = f"refresh_token:{refresh_token_hash}"
            session_id = await self.redis.get(refresh_token_key)
            
            if session_id:
                # Convert bytes to string if needed
                if isinstance(session_id, bytes):
                    session_id = session_id.decode()
                return session_id
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to lookup session by refresh token: {e}")
            return None

    async def refresh_session(self, session_id: str) -> bool:
        """
        Refresh session activity timestamp and extend TTL.

        Should be called on each authenticated request to prevent
        session expiration during active use.

        Args:
            session_id: Session identifier to refresh

        Returns:
            True if session was refreshed, False if session doesn't exist

        Example:
            >>> refreshed = await service.refresh_session(session_id)
            >>> if not refreshed:
            ...     raise SessionExpiredError()
        """
        try:
            session_key = f"session:{session_id}"

            # Check if session exists
            exists = await self.redis.exists(session_key)
            if not exists:
                return False

            # Update last_active timestamp
            now = datetime.utcnow()
            await self.redis.hset(session_key, "last_active", now.isoformat())

            # Extend TTL on session
            await self.redis.expire(session_key, self.session_ttl)

            # Get only needed fields to extend TTL on all associated mappings (performance optimization)
            user_id, refresh_token_hash, client_session_token = await self.redis.hmget(
                session_key, "user_id", "refresh_token_hash", "client_session_token"
            )
            
            # Convert bytes to strings if needed
            if isinstance(user_id, bytes):
                user_id = user_id.decode()
            if isinstance(refresh_token_hash, bytes):
                refresh_token_hash = refresh_token_hash.decode()
            if isinstance(client_session_token, bytes):
                client_session_token = client_session_token.decode()
            
            # Extend TTL on user session set
            if user_id:
                user_sessions_key = f"user_sessions:{user_id}"
                await self.redis.expire(user_sessions_key, self.session_ttl)
            
            # CRITICAL: Extend TTL on refresh token mapping (prevents expiration-based logout)
            if refresh_token_hash:
                refresh_token_key = f"refresh_token:{refresh_token_hash}"
                await self.redis.expire(refresh_token_key, self.session_ttl)
            
            # CRITICAL: Extend TTL on client token mapping (prevents expiration-based logout)
            if client_session_token:
                client_token_key = f"client_token:{client_session_token}"
                await self.redis.expire(client_token_key, self.session_ttl)

            return True

        except Exception as e:
            logger.error(f"Failed to refresh session {session_id[:12]}...: {e}")
            return False

    async def logout(self, session_id: str) -> bool:
        """
        Logout a single session (single device).

        Deletes session metadata, removes from user's session set,
        and cleans up refresh token mapping if exists.

        Args:
            session_id: Session identifier to logout

        Returns:
            True if session was deleted, False if session didn't exist

        Example:
            >>> success = await service.logout(session_id)
            >>> print(f"Logged out: {success}")
        """
        try:
            session_key = f"session:{session_id}"

            # Get session data before deleting (need user_id and refresh_token_hash)
            session_data = await self.redis.hgetall(session_key)
            if not session_data:
                return False

            # Convert bytes to strings if needed
            if session_data and isinstance(next(iter(session_data.keys())), bytes):
                session_data = {k.decode(): v.decode() for k, v in session_data.items()}

            user_id = session_data.get("user_id")
            refresh_token_hash = session_data.get("refresh_token_hash")
            client_session_token = session_data.get("client_session_token")
            
            if not user_id:
                return False

            # Delete session
            deleted = await self.redis.delete(session_key)

            # Remove from user's session set
            user_sessions_key = f"user_sessions:{user_id}"
            await self.redis.srem(user_sessions_key, session_id)
            
            # Delete refresh token mapping if exists
            if refresh_token_hash:
                refresh_token_key = f"refresh_token:{refresh_token_hash}"
                await self.redis.delete(refresh_token_key)
                logger.debug(f"Deleted refresh token mapping for session {session_id[:12]}...")
            
            # Delete client token mapping if exists
            if client_session_token:
                client_token_key = f"client_token:{client_session_token}"
                await self.redis.delete(client_token_key)
                logger.debug(f"Deleted client token mapping for session {session_id[:12]}...")

            if deleted:
                logger.info(
                    f"Logged out session {session_id[:12]}... for user {user_id[:8]}..."
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to logout session {session_id[:12]}...: {e}")
            return False

    async def logout_all_devices(self, user_id: str) -> int:
        """
        Logout all sessions for a user (all devices).

        Useful for security actions like password change or account
        compromise. Deletes all session metadata, clears session set,
        and removes all refresh token mappings.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions deleted

        Example:
            >>> count = await service.logout_all_devices("user_123")
            >>> print(f"Logged out {count} devices")
        """
        try:
            user_sessions_key = f"user_sessions:{user_id}"

            # Get all session IDs
            session_ids = await self.redis.smembers(user_sessions_key)

            if not session_ids:
                return 0

            # Convert bytes to strings if needed
            if session_ids and isinstance(next(iter(session_ids)), bytes):
                session_ids = {sid.decode() for sid in session_ids}

            # First, get refresh_token_hashes and client_session_tokens from all sessions before deleting
            pipe = self.redis.pipeline()
            for session_id in session_ids:
                session_key = f"session:{session_id}"
                pipe.hget(session_key, "refresh_token_hash")
                pipe.hget(session_key, "client_session_token")
            results = await pipe.execute()
            
            # Separate refresh token hashes and client tokens (interleaved results)
            refresh_token_hashes = [results[i] for i in range(0, len(results), 2)]
            client_session_tokens = [results[i] for i in range(1, len(results), 2)]
            
            # Batch delete all session keys and their refresh token mappings
            pipe = self.redis.pipeline()
            for session_id in session_ids:
                session_key = f"session:{session_id}"
                pipe.delete(session_key)
            
            # Delete refresh token mappings
            refresh_tokens_deleted = 0
            for token_hash in refresh_token_hashes:
                if token_hash:
                    if isinstance(token_hash, bytes):
                        token_hash = token_hash.decode()
                    refresh_token_key = f"refresh_token:{token_hash}"
                    pipe.delete(refresh_token_key)
                    refresh_tokens_deleted += 1
            
            # Delete client token mappings
            client_tokens_deleted = 0
            for client_token in client_session_tokens:
                if client_token:
                    if isinstance(client_token, bytes):
                        client_token = client_token.decode()
                    client_token_key = f"client_token:{client_token}"
                    pipe.delete(client_token_key)
                    client_tokens_deleted += 1
            
            results = await pipe.execute()
            # Count only session deletions (first len(session_ids) results are session deletions)
            count = sum(1 for i, result in enumerate(results) if i < len(session_ids) and result)

            # Clear user's session set
            await self.redis.delete(user_sessions_key)

            logger.info(
                f"Logged out {count} sessions for user {user_id[:8]}... "
                f"(deleted {refresh_tokens_deleted} refresh token mappings, "
                f"{client_tokens_deleted} client token mappings)"
            )
            return count

        except Exception as e:
            logger.error(
                f"Failed to logout all devices for user {user_id[:8]}...: {e}"
            )
            return 0

    async def list_sessions(self, user_id: str) -> List[SessionInfo]:
        """
        List all active sessions for a user.

        Returns session metadata for all devices. Useful for displaying
        "Active Sessions" in user settings.

        Args:
            user_id: User identifier

        Returns:
            List of SessionInfo objects

        Example:
            >>> sessions = await service.list_sessions("user_123")
            >>> for session in sessions:
            ...     print(f"{session.device_type}: {session.created_at}")
        """
        try:
            user_sessions_key = f"user_sessions:{user_id}"

            # Get all session IDs
            session_ids = await self.redis.smembers(user_sessions_key)

            if not session_ids:
                return []

            # Convert bytes to strings if needed
            if session_ids and isinstance(next(iter(session_ids)), bytes):
                session_ids = {sid.decode() for sid in session_ids}

            # Fetch all sessions
            sessions = []
            for session_id in session_ids:
                session_info = await self.validate_session(session_id)
                if session_info:  # Only include valid, non-expired sessions
                    sessions.append(session_info)

            return sessions

        except Exception as e:
            logger.error(f"Failed to list sessions for user {user_id[:8]}...: {e}")
            return []

    async def get_session_count(self, user_id: str) -> int:
        """
        Get number of active sessions for user.

        Args:
            user_id: User identifier

        Returns:
            Number of active sessions

        Example:
            >>> count = await service.get_session_count("user_123")
            >>> print(f"Active sessions: {count}")
        """
        try:
            user_sessions_key = f"user_sessions:{user_id}"
            count = await self.redis.scard(user_sessions_key)
            return count

        except Exception as e:
            logger.error(
                f"Failed to get session count for user {user_id[:8]}...: {e}"
            )
            return 0

    async def cleanup_expired_sessions(self, user_id: str) -> int:
        """
        Remove expired sessions from user's session set.

        Redis TTL handles session detail expiration automatically, but
        the session set may contain references to expired sessions.
        This method cleans up those references.

        Args:
            user_id: User identifier

        Returns:
            Number of expired sessions removed

        Example:
            >>> removed = await service.cleanup_expired_sessions("user_123")
            >>> print(f"Cleaned up {removed} expired sessions")
        """
        try:
            user_sessions_key = f"user_sessions:{user_id}"

            # Get all session IDs
            session_ids = await self.redis.smembers(user_sessions_key)

            if not session_ids:
                return 0

            # Convert bytes to strings if needed
            if session_ids and isinstance(next(iter(session_ids)), bytes):
                session_ids = {sid.decode() for sid in session_ids}

            # Batch EXISTS checks using Redis pipeline for efficiency
            pipe = self.redis.pipeline()
            session_keys = [f"session:{session_id}" for session_id in session_ids]
            for session_key in session_keys:
                pipe.exists(session_key)
            exists_results = await pipe.execute()

            # Batch remove sessions that don't exist (O(1) instead of O(N))
            expired_session_ids = [
                session_id for session_id, exists in zip(session_ids, exists_results)
                if not exists
            ]
            
            if expired_session_ids:
                await self.redis.srem(user_sessions_key, *expired_session_ids)
                removed_count = len(expired_session_ids)
            else:
                removed_count = 0

            if removed_count > 0:
                logger.info(
                    f"Cleaned up {removed_count} expired sessions for user {user_id[:8]}..."
                )

            return removed_count

        except Exception as e:
            logger.error(
                f"Failed to cleanup expired sessions for user {user_id[:8]}...: {e}"
            )
            return 0
    
    async def find_session_by_client_token(self, client_token: str, user_id: str) -> Optional[str]:
        """
        Find the real session_id from a client_session_token.
        
        Uses O(1) Redis lookup with O(n) fallback for legacy sessions.
        Client tokens are HMAC-signed tokens that frontends can safely store
        in localStorage.
        
        Args:
            client_token: The client_session_token from frontend (starts with cst_sess_)
            user_id: User ID to limit search scope
            
        Returns:
            Real session_id if found, None otherwise
            
        Example:
            >>> session_id = await service.find_session_by_client_token("cst_sess_abc...", "user_123")
            >>> if session_id:
            ...     await service.logout(session_id)
        """
        try:
            # O(1) lookup: try direct Redis mapping first
            client_token_key = f"client_token:{client_token}"
            session_id = await self.redis.get(client_token_key)
            if session_id:
                if isinstance(session_id, bytes):
                    session_id = session_id.decode()
                logger.debug(
                    f"Mapped client token {client_token[:12]}... to session {session_id[:12]}... (O(1) Redis lookup)"
                )
                return session_id
            
            # Fallback: O(n) search for legacy sessions without mapping
            logger.debug("Client token not in Redis mapping, trying O(n) fallback search")
            sessions = await self.list_sessions(user_id)
            
            # Find matching session by client token
            for session in sessions:
                if session.client_session_token == client_token:
                    logger.debug(
                        f"Mapped client token {client_token[:12]}... to session {session.session_id[:12]}... (O(n) fallback)"
                    )
                    # Re-create the mapping for next time
                    await self.redis.set(client_token_key, session.session_id, ex=self.session_ttl)
                    return session.session_id
            
            logger.warning(
                f"No session found for client token {client_token[:12]}... and user {user_id[:8]}..."
            )
            return None
            
        except Exception as e:
            logger.error(
                f"Failed to find session by client token {client_token[:12]}...: {e}"
            )
            return None
