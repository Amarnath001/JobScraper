from abc import ABC, abstractmethod

from app.schemas.job import NormalizedJob


class BaseScraper(ABC):
    def __init__(self, company_name: str, careers_url: str, source_config: dict) -> None:
        self.company_name = company_name
        self.careers_url = careers_url
        self.source_config = source_config

    @abstractmethod
    async def fetch_raw_jobs(self) -> list[dict]:
        pass

    @abstractmethod
    def normalize_job(self, raw_job: dict) -> NormalizedJob:
        pass

    async def scrape(self) -> list[NormalizedJob]:
        raw = await self.fetch_raw_jobs()
        return [self.normalize_job(r) for r in raw]
