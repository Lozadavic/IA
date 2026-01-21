from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.whatsapp import router as whatsapp_router
from app.utils import configure_logging


load_dotenv()
configure_logging()

app = FastAPI(title="WhatsApp Support Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(whatsapp_router, prefix="/webhook")


@app.get("/")
def health_check() -> dict:
    return {"status": "ok"}
