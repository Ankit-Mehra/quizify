import os
from fastapi import HTTPException, Request, Form
from supabase import create_client, Client
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
# Initialize Supabase client
supabase: Client = create_client(
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY")
)

templates = Jinja2Templates(directory="templates")

def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

def signup(email: str = Form(...), password: str = Form(...)):
    try:
        supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        return RedirectResponse(url="/dashboard", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def login(email: str = Form(...), password: str = Form(...)):
    try:
        supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return RedirectResponse(url="/dashboard", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def logout():
    try:
        supabase.auth.sign_out()
        return {"message": "Logout successful"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def verify_email(email: str):
    try:
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="User not found")
        return {"message": "Verification email sent"}  # TODO: implement actual email
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def change_password(email: str, new_password: str):
    try:
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="User not found")

        supabase.table("users").update({"password": new_password}).eq("email", email).execute()
        return {"message": "Password updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def delete_account(email: str):
    try:
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="User not found")

        supabase.table("users").delete().eq("email", email).execute()
        return {"message": "Account deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def update_email(email: str, new_email: str):
    try:
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="User not found")

        supabase.table("users").update({"email": new_email}).eq("email", email).execute()
        return {"message": "Email updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
