"""
Discover ATS from a careers page (follows job/search links from the landing page).

  python scripts/discover_company_source.py "Intuit" "https://jobs.intuit.com/search-jobs"
"""

from __future__ import annotations

import argparse
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

import httpx

from app.services.ats_discovery_service import discover_careers_site, format_discovery_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover ATS type from a careers site")
    parser.add_argument("company_name", help="Company display name")
    parser.add_argument("careers_url", help="Careers landing page URL")
    parser.add_argument(
        "--max-follow",
        type=int,
        default=5,
        help="Max job-related links to inspect after landing page (default: 5)",
    )
    args = parser.parse_args()

    timeout = httpx.Timeout(float(os.environ.get("SCRAPE_TIMEOUT_SECONDS", "60")))
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        result = discover_careers_site(client, args.careers_url, max_follow=args.max_follow)

    print(format_discovery_result(args.company_name, args.careers_url, result))


if __name__ == "__main__":
    main()
