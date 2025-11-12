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
import logging
import uuid
from datetime import datetime
from typing import List, Optional

import redis.asyncio as redis
from pydantic import BaseModel, Field

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

    @property
    def is_expired(self) -> bool:
        """Check if session is older than 24 hours"""
        age = datetime.utcnow() - self.last_active
        return age.total_seconds() > 86400  # 24 hours


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

    def __init__(self, user_id: str, count: int, max_sessions: int = 10):
        self.user_id = user_id
        self.count = count
        self.max_sessions = max_sessions
        super().__init__(
            f"User {user_id} has {count} active sessions (max: {max_sessions})"
        )


class SessionService:
    """
    Manages user authentication sessions using Redis.

    Provides multi-device session tracking, logout-all-devices,
    and session activity monitoring. Sessions expire after 24 hours
    of inactivity.

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

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize session service.

        Args:
            redis_client: Async Redis client instance
        """
        self.redis = redis_client
        self.session_ttl = 86400  # 24 hours

    @staticmethod
    def _hash_ip(ip_address: str) -> str:
        """Hash IP address for privacy"""
        return hashlib.sha256(ip_address.encode()).hexdigest()[:16]

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

    async def create_session(
        self,
        user_id: str,
        device_type: str = "browser",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> str:
        """
        Create a new authentication session.

        Generates a unique session ID, stores session metadata in Redis,
        and adds session to user's active session set.

        Args:
            user_id: User identifier
            device_type: Type of device ('browser', 'mobile', 'api')
            ip_address: Client IP address (will be hashed)
            user_agent: Client user agent string (will be truncated)

        Returns:
            session_id: Unique session identifier (UUID)

        Raises:
            TooManySessionsError: If user has >10 active sessions
            redis.RedisError: If Redis operation fails

        Example:
            >>> session_id = await service.create_session(
            ...     user_id="user_123",
            ...     device_type="browser",
            ...     ip_address="192.168.1.1",
            ...     user_agent="Mozilla/5.0..."
            ... )
        """
        try:
            # Check session count limit
            session_count = await self.get_session_count(user_id)
            if session_count >= 10:
                logger.warning(
                    f"User {user_id[:8]}... has too many sessions: {session_count}"
                )
                raise TooManySessionsError(user_id, session_count, max_sessions=10)

            # Generate session ID
            session_id = self._generate_session_id()

            # Prepare session metadata
            now = datetime.utcnow()
            hashed_ip = self._hash_ip(ip_address) if ip_address else "unknown"
            truncated_ua = (
                self._truncate_user_agent(user_agent) if user_agent else "unknown"
            )

            session_data = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": now.isoformat(),
                "last_active": now.isoformat(),
                "device_type": device_type,
                "ip_address": hashed_ip,
                "user_agent": truncated_ua,
            }

            # Store session in Redis hash
            session_key = f"session:{session_id}"
            await self.redis.hset(session_key, mapping=session_data)
            await self.redis.expire(session_key, self.session_ttl)

            # Add to user's session set
            user_sessions_key = f"user_sessions:{user_id}"
            await self.redis.sadd(user_sessions_key, session_id)
            await self.redis.expire(user_sessions_key, self.session_ttl)

            logger.info(
                f"Created session for user {user_id[:8]}... on {device_type} device"
            )
            return session_id

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
                    k.decode(): v.decode() for k, v in session_data.items()
                }

            # Parse datetime fields
            session_data["created_at"] = datetime.fromisoformat(
                session_data["created_at"]
            )
            session_data["last_active"] = datetime.fromisoformat(
                session_data["last_active"]
            )

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

            # Extend TTL
            await self.redis.expire(session_key, self.session_ttl)

            return True

        except Exception as e:
            logger.error(f"Failed to refresh session {session_id[:12]}...: {e}")
            return False

    async def logout(self, session_id: str) -> bool:
        """
        Logout a single session (single device).

        Deletes session metadata and removes from user's session set.

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

            # Get user_id before deleting
            user_id = await self.redis.hget(session_key, "user_id")
            if not user_id:
                return False

            if isinstance(user_id, bytes):
                user_id = user_id.decode()

            # Delete session
            deleted = await self.redis.delete(session_key)

            # Remove from user's session set
            user_sessions_key = f"user_sessions:{user_id}"
            await self.redis.srem(user_sessions_key, session_id)

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
        compromise. Deletes all session metadata and clears session set.

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

            # Delete all sessions
            count = 0
            for session_id in session_ids:
                session_key = f"session:{session_id}"
                deleted = await self.redis.delete(session_key)
                if deleted:
                    count += 1

            # Clear user's session set
            await self.redis.delete(user_sessions_key)

            logger.info(f"Logged out {count} sessions for user {user_id[:8]}...")
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

            # Check each session
            removed_count = 0
            for session_id in session_ids:
                session_key = f"session:{session_id}"
                exists = await self.redis.exists(session_key)

                if not exists:
                    # Remove from set if session doesn't exist
                    await self.redis.srem(user_sessions_key, session_id)
                    removed_count += 1

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
