from fastapi import FastAPI
from app.api.routes import load_publications, publications

app = FastAPI(title="Publications Microservice")

app.include_router(load_publications.router)
app.include_router(publications.router)
