from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from api import auth_routes, quiz_routes
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
app = FastAPI(
    title="Quiz Generator",
    description="Generate quizzes from text",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.include_router(quiz_routes.router, prefix="/api")
app.include_router(auth_routes.router, prefix="/api")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

# Security scheme for Swagger UI
bearer_scheme = HTTPBearer()

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    # Do NOT apply globally — individual routes will declare Depends
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi