from fastapi import FastAPI
from app.api.routes import load_publications, load_oai_publications, publications, metrics, social_media_records, social_media_metrics, export_excel, classification_report
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from app.services.database_init_service import init_database, verify_database_connection
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

method_dict = {"method": "embeddings"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database on startup
    logger.info("Starting application initialization...")
    
    # Verify database connection
    connection_ok = await verify_database_connection()
    if not connection_ok:
        logger.warning("Database connection verification failed, but continuing with initialization...")
    
    # Create tables if they don't exist
    await init_database()
    logger.info("Database initialization completed successfully")
    
    # Start the scheduler for weekly publications job
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
    logger.info("Scheduler started successfully")

    yield

    logger.info("Shutting down scheduler...")
    scheduler.shutdown()


app = FastAPI(
    title="Publications Microservice",
    lifespan=lifespan,
)

app.include_router(load_publications.router)
app.include_router(load_oai_publications.router)
app.include_router(publications.router)
app.include_router(metrics.router)
app.include_router(social_media_records.router)
app.include_router(social_media_metrics.router)
app.include_router(export_excel.router)
app.include_router(classification_report.router)

# CORS Middleware
app.add_middleware(
  CORSMiddleware,
  allow_origins=['http://localhost:5173', 'https://observatorio-ia.vercel.app'],
  allow_methods=['*'],
  allow_headers=['*'],
)