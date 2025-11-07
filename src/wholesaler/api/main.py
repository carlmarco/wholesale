"""
FastAPI Main Application

Wholesaler Lead Management System REST API.
"""
from datetime import datetime
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from src.wholesaler.api.dependencies import get_db
from src.wholesaler.api.schemas import HealthCheck
from src.wholesaler.api.routers import leads, properties, stats

# Create FastAPI app
app = FastAPI(
    title="Wholesaler Lead Management API",
    description="REST API for managing and scoring real estate wholesale leads",
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],  # Streamlit default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(leads.router)
app.include_router(properties.router)
app.include_router(stats.router)


@app.get("/health", response_model=HealthCheck, tags=["health"])
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint.

    Returns:
        Health status with database connectivity check
    """
    # Test database connection
    try:
        db.execute("SELECT 1")
        database_status = "connected"
    except Exception as e:
        database_status = f"error: {str(e)}"

    return HealthCheck(
        status="healthy" if database_status == "connected" else "degraded",
        version="0.3.0",
        database=database_status,
        timestamp=datetime.utcnow(),
    )


@app.get("/", tags=["root"])
def root():
    """
    Root endpoint.

    Returns:
        API information
    """
    return {
        "name": "Wholesaler Lead Management API",
        "version": "0.3.0",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.wholesaler.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
