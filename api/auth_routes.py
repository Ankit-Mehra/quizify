from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from services.auth_handlers import (
    signup, login, logout,
    verify_email, change_password,
    delete_account, update_email,
    login_page, signup_page
)

router = APIRouter(prefix="/auth", tags=["Auth"])
templates = Jinja2Templates(directory="templates")

router.add_api_route("/signup_page", signup_page, methods=["GET"])
router.add_api_route("/signup", signup, methods=["POST"])
router.add_api_route("/login_page", login_page, methods=["GET"])
router.add_api_route("/login", login, methods=["POST"])
router.add_api_route("/logout", logout, methods=["POST"])
router.add_api_route("/verify-email", verify_email, methods=["POST"])
router.add_api_route("/change-password", change_password, methods=["POST"])
router.add_api_route("/delete-account", delete_account, methods=["POST"])
router.add_api_route("/update-email", update_email, methods=["POST"])
