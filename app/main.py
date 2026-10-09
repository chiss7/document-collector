from fastapi import FastAPI
from app.api.routes import load_publications, load_oai_publications, publications, metrics, social_media_records, social_media_metrics, export_excel, classification_report
# from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from app.services.database_init_service import init_database, verify_database_connection
from app.services.initial_data_service import load_initial_csv_data
from app.services.social_media_service import seed_from_excel_if_empty
from app.core.config import settings
from app.core.logging_middleware import RequestLoggingMiddleware
import logging

logger = logging.getLogger(__name__)

# scheduler = AsyncIOScheduler()

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

    if settings.LOAD_INITIAL_CSV_DATA:
        try:
            csv_counts = await load_initial_csv_data()
            logger.info("Initial CSV restore finished: %s", csv_counts)
        except Exception:
            logger.exception("Failed to restore tables from exports/initial_data")
    else:
        logger.info("LOAD_INITIAL_CSV_DATA is disabled; skipping CSV restore")

    try:
        inserted = await seed_from_excel_if_empty()
        if inserted:
            logger.info("Loaded %d social media records from ecuador_records.xlsx", inserted)
    except Exception:
        logger.exception("Failed to seed social_media_records from ecuador_records.xlsx")
    
    # Start the scheduler for weekly publications job
    # scheduler.add_job(
    #     load_publications.run_fetch_and_save,
    #     trigger="cron",
    #     day_of_week="sun",
    #     hour=0,
    #     minute=0,
    #     kwargs={"payload": method_dict},
    #     id="weekly_publications_job",
    #     replace_existing=True,
    # )
    # scheduler.start()
    # logger.info("Scheduler started successfully")

    yield

    # logger.info("Shutting down scheduler...")
    # scheduler.shutdown()


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

# Request/Response logging middleware (outermost so it captures every request)
if settings.REQUEST_LOGGING_ENABLED:
    app.add_middleware(RequestLoggingMiddleware)