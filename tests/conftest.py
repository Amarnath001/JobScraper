import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://jobscraper:jobscraper@localhost:5432/jobscraper",
)
