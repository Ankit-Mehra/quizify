#!/usr/bin/env python3
"""
Export Quizify users to CSV for Google Ads Customer Match
Format: https://support.google.com/google-ads/answer/7475964

Run: python scripts/export_google_ads.py
"""

import csv
import os
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def split_name(full_name: str) -> tuple[str, str]:
    """
    Split full name into first and last name.
    
    Google Ads requires lowercase names with no extra spaces.
    
    Args:
        full_name: Full name string
        
    Returns:
        Tuple of (first_name, last_name), lowercased
    """
    if not full_name or not full_name.strip():
        return ("", "")
    
    # Normalize: lowercase and strip extra spaces
    name = full_name.strip().lower()
    parts = name.split()
    
    if len(parts) == 0:
        return ("", "")
    elif len(parts) == 1:
        return (parts[0], "")
    else:
        # First word is first name, rest is last name
        return (parts[0], " ".join(parts[1:]))


def export_users_for_google_ads():
    """Export all verified users to Google Ads Customer Match CSV format"""
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    # Get all users from auth.users (with pagination)
    all_users = []
    page = 1
    per_page = 100
    
    while True:
        result = supabase.auth.admin.list_users(page=page, per_page=per_page)
        if not result:
            break
        all_users.extend(result)
        if len(result) < per_page:
            break
        page += 1
    
    print(f"📊 Found {len(all_users)} total users in database")
    
    users = []
    for user in all_users:
        if user.email and user.email_confirmed_at:  # Only verified emails
            # Get name from metadata
            full_name = ""
            if user.user_metadata and user.user_metadata.get("name"):
                full_name = user.user_metadata.get("name", "")
            
            first_name, last_name = split_name(full_name)
            
            # Google Ads requires lowercase emails with no extra spaces
            email = user.email.strip().lower()
            
            users.append({
                "Email": email,
                "First Name": first_name,
                "Last Name": last_name,
                "Country": "",  # We don't collect this
                "Zip": "",      # We don't collect this
            })
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"quizify_google_ads_{timestamp}.csv"
    filepath = os.path.join(os.path.dirname(__file__), filename)
    
    # Write CSV (Google Ads format)
    fieldnames = ["Email", "First Name", "Last Name", "Country", "Zip"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(users)
    
    print(f"✅ Exported {len(users)} users to: {filepath}")
    print(f"\nGoogle Ads Customer Match CSV Preview (first 5):")
    print("-" * 70)
    print(f"{'Email':<35} {'First Name':<15} {'Last Name':<15}")
    print("-" * 70)
    for user in users[:5]:
        print(f"{user['Email']:<35} {user['First Name']:<15} {user['Last Name']:<15}")
    if len(users) > 5:
        print(f"  ... and {len(users) - 5} more")
    
    print(f"\n📋 Format: Google Ads Customer Match (Email, First Name, Last Name, Country, Zip)")
    print("📝 Note: Country and Zip are empty (not collected)")
    
    return filepath


if __name__ == "__main__":
    export_users_for_google_ads()
