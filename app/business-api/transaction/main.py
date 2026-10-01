import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from logging_config import configure_logging
from mcp_tools import mcp
import logging

# import the transaction router we just added
from routers import router as transaction_routers
from dispute_routers import router as dispute_routers

logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    # Initialize logging for the app
    configure_logging()
    logger = logging.getLogger(__name__)
    
  
   #Add mcp server to the FastAPI app
    mcp_app = mcp.http_app(path='/')
    app = FastAPI(title="Transaction API and MCP server", lifespan=mcp_app.lifespan)
    app.mount("/mcp", mcp_app)

    # Include the transaction router
    app.include_router(transaction_routers, prefix="/api/transactions", tags=["transactions"]) 
    app.include_router(dispute_routers, prefix="/api/support-cases", tags=["support-cases"])

    allowed_origins = [
        origin.strip()
        for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5170").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    logger.info("FastAPI application created successfully")
    return app

app = create_app()

if __name__ == "__main__":
 
    profile = os.environ.get("PROFILE", "prod")
    port = 8071 if profile == "dev" else 8080
    logger.info(f"Starting transaction service server with profile: {profile}, port: {port}")
    #run app as uvicorn server
    uvicorn.run("main:app", host="0.0.0.0", port=port)
