from enum import Enum
import os

from dotenv import load_dotenv

load_dotenv()


class AuditAction(Enum):
    INSERT_LSP = "INSERT_LSP"
    UPDATE_LSP = "UPDATE_LSP"
    DELETE_LSP = "DELETE_LSP"
    INSERT_USER = "INSERT_USER"
    UPDATE_USER = "UPDATE_USER"
    DELETE_USER = "DELETE_USER"
    RESET_PWD = "RESET_PWD"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    URL_FINDER = "URL_FINDER"
    LSP_SUMMARY = "LSP_SUMMARY"
    CRAWL = "CRAWL"


class CrawlStatus(Enum):
    COMPLETED = "Completed"  # All data fetched successfully
    PARTIAL = "Partial"  # Some data missing Amount/Portfolio/As on date
    ERROR = "Error"  # Error during fetch/parse
    MISSING = "Missing"  # DLG URL MISSING
    STALE = "Stale"  # as on date MISSING
    NO_DATA = "NoData"  # PAGE AVAILABLE DATA NOT AVAILABLE


class LSPType(Enum):
    BANK = "Bank"
    NBFC = "NBFC"
    NBFC_AA = "NBFC-AA"
    NBFC_FINTECH = "NBFC-FinTech"
    LENDING_TECH_WITH_INHOUSE_NBFC = "Lending Tech With In-house NBFC"
    LENDING_TECH_WITHOUT_INHOUSE_NBFC = "Lending Tech Without In-house NBFC"
    MARKETPLACE = "Marketplace"
    MULTIPRODUCT = "Multiproduct"
    OTHER = "Other"


default_password = os.getenv("DEFAULT_PASSWORD", "Welcome@123")
