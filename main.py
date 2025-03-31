from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from api import quiz_generator

app = FastAPI(
    title="Quiz Generator",
    description="Generate quizzes from text",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.include_router(quiz_generator.router, prefix="/api")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
