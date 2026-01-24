from fastapi import FastAPI
from app.api.routes import load_publications, publications
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager


scheduler = AsyncIOScheduler()

method_dict = {"method": "regex"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        load_publications.run_fetch_and_save,
        trigger="cron",
        day_of_week="sun",
        hour=0,
        minute=0,
        kwargs={"payload": method_dict},
        id="weekly_publications_job",
        replace_existing=True,
    )
    scheduler.start()

    yield

    scheduler.shutdown()


app = FastAPI(
    title="Publications Microservice",
    lifespan=lifespan,
)

app.include_router(load_publications.router)
app.include_router(publications.router)