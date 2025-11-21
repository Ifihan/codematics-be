from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from app.config import settings
from app.api import v1
from app.db.database import Base, engine

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug
)

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup (non-blocking)"""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        # Log error but don't fail startup
        print(f"Warning: Database initialization failed: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1.router)


@app.get("/")
def root():
    """Redirect to API documentation"""
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "healthy"}