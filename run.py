#!/usr/bin/env python3
import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8004,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
