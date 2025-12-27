"""
Supabase Flashcard Database Service.

This module provides database operations for flashcard decks and cards,
following the same patterns as supabase_quiz.py.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from config import config as app_config
from services.logger import app_logger as logger
from schemas.flashcard import (
    GeneratedFlashcard,
)


# Lazy load Supabase client to avoid initialization issues in tests
def get_supabase():
    """Get Supabase client (lazy loaded)"""
    return app_config.get_supabase_client()


def get_authed_supabase_client(user_token: str):
    """Returns Supabase client with user's JWT token for RLS enforcement"""
    logger.debug(f"Creating authenticated Supabase client with token: {user_token[:4]}...")
    return app_config.get_authenticated_supabase_client(user_token)


# =============================================================================
# Deck Operations
# =============================================================================

def create_deck(
    user_id: str,
    title: str,
    user_token: Optional[str] = None,
    description: Optional[str] = None,
    content_source_type: Optional[str] = None,
    content_source_reference: Optional[str] = None,
    generation_mode: str = "standard",
) -> Dict[str, Any]:
    """
    Create a new flashcard deck.
    
    Args:
        user_id: ID of the user creating the deck
        title: Title of the deck
        user_token: JWT token for RLS enforcement
        description: Optional description
        content_source_type: Source type (text, file, url)
        content_source_reference: Reference to source
        generation_mode: "standard" (1 credit) or "enhanced" (2 credits)
        
    Returns:
        Created deck data
    """
    logger.info("Creating flashcard deck for user %s...: %s (mode: %s)", user_id[:8], title, generation_mode)
    
    # Use authenticated client if token provided
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    deck_data = {
        "created_by": user_id,
        "title": title,
        "description": description,
        "content_source_type": content_source_type,
        "content_source_reference": content_source_reference,
        "generation_mode": generation_mode,
    }
    
    result = supabase.table("flashcard_decks").insert(deck_data).execute()
    
    if not result.data:
        raise Exception("Failed to create flashcard deck")
    
    logger.info("Created deck %s for user %s...", result.data[0]["id"], user_id[:8])
    return result.data[0]


def get_deck(
    deck_id: str,
    user_id: str,
    user_token: Optional[str] = None,
    include_cards: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Get a flashcard deck by ID.
    
    Args:
        deck_id: ID of the deck
        user_id: ID of the requesting user (for RLS)
        user_token: JWT token for RLS enforcement
        include_cards: Whether to include cards in response
        
    Returns:
        Deck data or None if not found
    """
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    result = supabase.table("flashcard_decks")\
        .select("*")\
        .eq("id", deck_id)\
        .single()\
        .execute()
    
    if not result.data:
        return None
    
    deck = result.data
    
    if include_cards:
        cards_result = supabase.table("flashcards")\
            .select("*")\
            .eq("deck_id", deck_id)\
            .order("position")\
            .execute()
        deck["cards"] = cards_result.data or []
    
    return deck


def get_user_decks(
    user_id: str,
    user_token: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Get all decks for a user.
    
    Args:
        user_id: ID of the user
        user_token: JWT token for RLS enforcement
        limit: Maximum number of decks to return
        offset: Offset for pagination
        
    Returns:
        List of deck data
    """
    logger.debug("Getting decks for user %s...", user_id[:8])
    
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    result = supabase.table("flashcard_decks")\
        .select("*")\
        .eq("created_by", user_id)\
        .order("created_at", desc=True)\
        .range(offset, offset + limit - 1)\
        .execute()
    
    return result.data or []


def update_deck(
    deck_id: str,
    user_id: str,
    user_token: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update a flashcard deck.
    
    Args:
        deck_id: ID of the deck to update
        user_id: ID of the user (for RLS)
        user_token: JWT token for RLS enforcement
        title: New title
        description: New description
        
    Returns:
        Updated deck data or None if not found
    """
    logger.info("Updating deck %s for user %s...", deck_id, user_id[:8])
    
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    update_data = {}
    if title is not None:
        update_data["title"] = title
    if description is not None:
        update_data["description"] = description
    
    if not update_data:
        return get_deck(deck_id, user_id, user_token)
    
    result = supabase.table("flashcard_decks")\
        .update(update_data)\
        .eq("id", deck_id)\
        .execute()
    
    return result.data[0] if result.data else None


def delete_deck(
    deck_id: str,
    user_id: str,
    user_token: Optional[str] = None,
) -> bool:
    """
    Delete a flashcard deck and all its cards.
    
    Args:
        deck_id: ID of the deck to delete
        user_id: ID of the user (for RLS)
        user_token: JWT token for RLS enforcement
        
    Returns:
        True if deleted, False otherwise
    """
    logger.info("Deleting deck %s for user %s...", deck_id, user_id[:8])
    
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    # Cards will be cascade deleted due to foreign key
    result = supabase.table("flashcard_decks")\
        .delete()\
        .eq("id", deck_id)\
        .execute()
    
    return len(result.data) > 0 if result.data else False


# =============================================================================
# Flashcard Operations
# =============================================================================

def create_flashcards_batch(
    deck_id: str,
    cards: List[GeneratedFlashcard],
    user_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Create multiple flashcards in a deck.
    
    Supports both standard and enhanced mode cards.
    Enhanced mode cards include additional metadata like
    concept_name, bloom_level, difficulty_score, and source_chunk_id.
    
    Args:
        deck_id: ID of the deck
        cards: List of flashcards to create
        user_token: JWT token for RLS enforcement
        
    Returns:
        List of created flashcard data
    """
    logger.info("Creating %d flashcards in deck %s", len(cards), deck_id)
    
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    card_data = []
    for i, card in enumerate(cards):
        card_entry = {
            "deck_id": deck_id,
            "front": card.front,
            "back": card.back,
            "hint": card.hint,
            "position": i,
        }
        
        # Add enhanced mode fields if present
        if hasattr(card, 'concept_name') and card.concept_name:
            card_entry["concept_name"] = card.concept_name
        if hasattr(card, 'bloom_level') and card.bloom_level:
            card_entry["bloom_level"] = card.bloom_level
        if hasattr(card, 'difficulty_score') and card.difficulty_score is not None:
            card_entry["difficulty_score"] = card.difficulty_score
        if hasattr(card, 'source_chunk_id') and card.source_chunk_id:
            card_entry["source_chunk_id"] = card.source_chunk_id
        
        card_data.append(card_entry)
    
    result = supabase.table("flashcards").insert(card_data).execute()
    
    if not result.data:
        raise Exception("Failed to create flashcards")
    
    logger.info("Created %d flashcards in deck %s", len(result.data), deck_id)
    return result.data


def get_flashcard(
    card_id: str,
    user_token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get a single flashcard by ID.
    
    Args:
        card_id: ID of the flashcard
        user_token: JWT token for RLS enforcement
        
    Returns:
        Flashcard data or None if not found
    """
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    result = supabase.table("flashcards")\
        .select("*")\
        .eq("id", card_id)\
        .single()\
        .execute()
    
    return result.data


def get_deck_cards(
    deck_id: str,
    user_token: Optional[str] = None,
    status_filter: Optional[List[str]] = None,
    limit: Optional[int] = None,
    shuffle: bool = False,
) -> List[Dict[str, Any]]:
    """
    Get all flashcards in a deck.
    
    Args:
        deck_id: ID of the deck
        user_token: JWT token for RLS enforcement
        status_filter: Filter by card status (new, learning, review, mastered)
        limit: Maximum number of cards to return
        shuffle: If True, return cards in random order
        
    Returns:
        List of flashcard data
    """
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    query = supabase.table("flashcards").select("*").eq("deck_id", deck_id)
    
    if status_filter:
        query = query.in_("status", status_filter)
    
    if not shuffle:
        query = query.order("position")
    
    if limit:
        query = query.limit(limit)
    
    result = query.execute()
    cards = result.data or []
    
    if shuffle:
        import random
        random.shuffle(cards)
    
    return cards


def update_flashcard(
    card_id: str,
    user_token: Optional[str] = None,
    front: Optional[str] = None,
    back: Optional[str] = None,
    hint: Optional[str] = None,
    status: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update a flashcard.
    
    Args:
        card_id: ID of the flashcard
        user_token: JWT token for RLS enforcement
        front: New front text
        back: New back text
        hint: New hint
        status: New status
        
    Returns:
        Updated flashcard data or None if not found
    """
    logger.debug("Updating flashcard %s", card_id)
    
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    update_data = {}
    if front is not None:
        update_data["front"] = front
    if back is not None:
        update_data["back"] = back
    if hint is not None:
        update_data["hint"] = hint
    if status is not None:
        update_data["status"] = status
    
    if not update_data:
        return get_flashcard(card_id, user_token)
    
    result = supabase.table("flashcards")\
        .update(update_data)\
        .eq("id", card_id)\
        .execute()
    
    return result.data[0] if result.data else None


def delete_flashcard(
    card_id: str,
    user_token: Optional[str] = None,
) -> bool:
    """
    Delete a flashcard.
    
    Args:
        card_id: ID of the flashcard to delete
        user_token: JWT token for RLS enforcement
        
    Returns:
        True if deleted, False otherwise
    """
    logger.debug("Deleting flashcard %s", card_id)
    
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    result = supabase.table("flashcards")\
        .delete()\
        .eq("id", card_id)\
        .execute()
    
    return len(result.data) > 0 if result.data else False


# =============================================================================
# Spaced Repetition Updates
# =============================================================================

def update_card_review(
    card_id: str,
    result: str,  # "again", "hard", "good", "easy"
    user_token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update a flashcard after a review (for spaced repetition).
    
    Implements a simplified SM2-like algorithm:
    - "again": Reset to learning state
    - "hard": Increase interval slightly
    - "good": Normal interval increase
    - "easy": Large interval increase
    
    Args:
        card_id: ID of the flashcard
        result: Review result
        user_token: JWT token for RLS enforcement
        
    Returns:
        Updated flashcard data
    """
    logger.debug("Updating card %s with review result: %s", card_id, result)
    
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    # Get current card data
    card = get_flashcard(card_id, user_token)
    if not card:
        return None
    
    # Calculate new values based on result
    ease_factor = float(card.get("ease_factor", 2.5))
    interval_days = int(card.get("interval_days", 0))
    repetitions = int(card.get("repetitions", 0))
    times_correct = int(card.get("times_correct", 0))
    times_incorrect = int(card.get("times_incorrect", 0))
    
    if result == "again":
        # Reset to learning
        new_status = "learning"
        new_interval = 0
        new_ease = max(1.3, ease_factor - 0.2)
        new_reps = 0
        times_incorrect += 1
    elif result == "hard":
        # Small interval increase
        new_status = "review" if repetitions >= 2 else "learning"
        new_interval = max(1, int(interval_days * 1.2))
        new_ease = max(1.3, ease_factor - 0.15)
        new_reps = repetitions + 1
        times_correct += 1
    elif result == "good":
        # Normal interval increase
        new_status = "review" if repetitions >= 2 else "learning"
        new_interval = max(1, int(interval_days * ease_factor)) if interval_days > 0 else 1
        new_ease = ease_factor
        new_reps = repetitions + 1
        times_correct += 1
    elif result == "easy":
        # Large interval increase
        new_status = "mastered" if repetitions >= 5 else "review"
        new_interval = max(1, int(interval_days * ease_factor * 1.3)) if interval_days > 0 else 4
        new_ease = min(3.0, ease_factor + 0.15)
        new_reps = repetitions + 1
        times_correct += 1
    else:
        # Default to "good" behavior
        new_status = card.get("status", "learning")
        new_interval = interval_days
        new_ease = ease_factor
        new_reps = repetitions
    
    # Calculate next review date
    from datetime import timedelta
    next_review = datetime.utcnow() + timedelta(days=new_interval) if new_interval > 0 else None
    
    update_data = {
        "status": new_status,
        "ease_factor": new_ease,
        "interval_days": new_interval,
        "repetitions": new_reps,
        "next_review": next_review.isoformat() if next_review else None,
        "last_reviewed": datetime.utcnow().isoformat(),
        "times_correct": times_correct,
        "times_incorrect": times_incorrect,
    }
    
    result_data = supabase.table("flashcards")\
        .update(update_data)\
        .eq("id", card_id)\
        .execute()
    
    return result_data.data[0] if result_data.data else None


# =============================================================================
# Study Session Operations
# =============================================================================

def create_study_session(
    deck_id: str,
    user_id: str,
    user_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new study session for a deck.
    
    Args:
        deck_id: ID of the deck
        user_id: ID of the user
        user_token: JWT token for RLS enforcement
        
    Returns:
        Created session data
    """
    logger.info("Creating study session for deck %s, user %s...", deck_id, user_id[:8])
    
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    session_data = {
        "deck_id": deck_id,
        "user_id": user_id,
    }
    
    result = supabase.table("flashcard_study_sessions").insert(session_data).execute()
    
    if not result.data:
        raise Exception("Failed to create study session")
    
    return result.data[0]


def complete_study_session(
    session_id: str,
    cards_studied: int,
    cards_correct: int,
    cards_incorrect: int,
    time_spent_seconds: int,
    user_token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Complete a study session with results.
    
    Args:
        session_id: ID of the session
        cards_studied: Number of cards studied
        cards_correct: Number of correct responses
        cards_incorrect: Number of incorrect responses
        time_spent_seconds: Total time spent
        user_token: JWT token for RLS enforcement
        
    Returns:
        Updated session data
    """
    logger.info("Completing study session %s", session_id)
    
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    update_data = {
        "cards_studied": cards_studied,
        "cards_correct": cards_correct,
        "cards_incorrect": cards_incorrect,
        "time_spent_seconds": time_spent_seconds,
        "completed_at": datetime.utcnow().isoformat(),
        "is_completed": True,
    }
    
    result = supabase.table("flashcard_study_sessions")\
        .update(update_data)\
        .eq("id", session_id)\
        .execute()
    
    # Also update the deck's last_studied timestamp
    if result.data:
        session = result.data[0]
        supabase.table("flashcard_decks")\
            .update({
                "last_studied": datetime.utcnow().isoformat(),
                "total_study_sessions": supabase.rpc(
                    "increment_study_sessions",
                    {"deck_id": session["deck_id"]}
                ) if False else None  # TODO: Create this RPC function
            })\
            .eq("id", session["deck_id"])\
            .execute()
    
    return result.data[0] if result.data else None


def get_user_study_sessions(
    user_id: str,
    user_token: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get recent study sessions for a user.
    
    Args:
        user_id: ID of the user
        user_token: JWT token for RLS enforcement
        limit: Maximum sessions to return
        
    Returns:
        List of session data
    """
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    result = supabase.table("flashcard_study_sessions")\
        .select("*, flashcard_decks(title)")\
        .eq("user_id", user_id)\
        .order("started_at", desc=True)\
        .limit(limit)\
        .execute()
    
    return result.data or []
