from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Raymond Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

# Example placeholder route; add your real endpoints under backend/fastapi_app/
@app.get("/api/info")
async def info():
    return {"name": "raymond-v2-8-trader", "version": "v2.8"}