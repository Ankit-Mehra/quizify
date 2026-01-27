#!/usr/bin/env python3
"""
Export Quizify users to CSV for Zoho Campaigns
Run: python scripts/export_users_csv.py
"""

import csv
import os
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def export_users_to_csv():
    """Export all verified users to CSV"""
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    # Get all users from auth.users
    result = supabase.auth.admin.list_users()
    
    users = []
    for user in result:
        if user.email and user.email_confirmed_at:  # Only verified emails
            # Get name, default to "Quizify User" if empty (Zoho doesn't like nulls)
            name = ""
            if user.user_metadata and user.user_metadata.get("name"):
                name = user.user_metadata.get("name", "").strip()
            if not name:
                name = "Quizify User"
            
            users.append({
                "email": user.email,
                "name": name,
            })
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"quizify_users_{timestamp}.csv"
    filepath = os.path.join(os.path.dirname(__file__), filename)
    
    # Write CSV
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "name"])
        writer.writeheader()
        writer.writerows(users)
    
    print(f"✅ Exported {len(users)} users to: {filepath}")
    print(f"\nCSV Preview (first 5):")
    print("-" * 50)
    for user in users[:5]:
        print(f"  {user['email']} | {user['name'] or '(no name)'}")
    if len(users) > 5:
        print(f"  ... and {len(users) - 5} more")
    
    return filepath


if __name__ == "__main__":
    export_users_to_csv()
