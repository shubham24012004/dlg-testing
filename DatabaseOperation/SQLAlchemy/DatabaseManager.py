"""
Singleton Database Manager for DLG Analysis.

Provides centralized CRUD operations for all tables with a single engine and session factory.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import (
    Base,
    LspMasterORM,
    DlgCrawlerConfigORM,
    DlgRawORM,
    AuditLogORM,
    AuditAction,
)

logger = logging.getLogger(__name__)

# Module-level singleton instance
_db_manager: Optional[DatabaseManager] = None


class DatabaseManager:
    """Singleton database manager with CRUD operations for all tables.
    
    Provides:
    - Single engine and session factory (no multiple connections)
    - Context manager for session lifecycle
    - CRUD operations for LspMaster, DlgCrawlerConfig, DlgRaw, AuditLog
    - Transaction management with automatic commit/rollback
    """

    def __init__(self, db_path: str = None):
        """Initialize database manager with a single engine and session factory.
        
        Args:
            db_path: Path to SQLite database file. Defaults to DLG_SQLITE_PATH env var.
        """
        if db_path is None:
            db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")
        
        self.db_path = db_path
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            future=True,
            pool_pre_ping=True,  # Verify connections before using
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        
        # Create all tables
        Base.metadata.create_all(self.engine)
        logger.info("DatabaseManager initialized with db_path=%s", db_path)

    @contextmanager
    def get_session(self):
        """Context manager for database sessions with automatic commit/rollback.
        
        Usage:
            with db_manager.get_session() as session:
                result = session.query(Model).all()
        
        Yields:
            Session: SQLAlchemy session
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ==================== LspMaster CRUD ====================

    def create_lsp_master(
        self, name: str, home_url: str = None, active: bool = True, session: Session = None
    ) -> LspMasterORM:
        """Create a new LSP master record.
        
        Args:
            name: LSP name (required)
            home_url: LSP home URL
            active: Whether LSP is active
            session: Optional session (if None, creates a new one)
        
        Returns:
            Created LspMasterORM instance
        """
        def _create(sess: Session) -> LspMasterORM:
            lsp = LspMasterORM(name=name, home_url=home_url, active=active)
            sess.add(lsp)
            sess.flush()
            logger.debug("Created LSP master: id=%s name=%s", lsp.id, lsp.name)
            return lsp

        if session:
            return _create(session)
        else:
            with self.get_session() as sess:
                return _create(sess)

    def get_lsp_master(self, id: int, session: Session = None) -> Optional[LspMasterORM]:
        """Get LSP master by ID.
        
        Args:
            id: LSP ID
            session: Optional session
        
        Returns:
            LspMasterORM instance or None if not found
        """
        def _get(sess: Session) -> Optional[LspMasterORM]:
            return sess.query(LspMasterORM).filter_by(id=id).one_or_none()

        if session:
            return _get(session)
        else:
            with self.get_session() as sess:
                return _get(sess)

    def get_lsp_master_by_name(self, name: str, session: Session = None) -> Optional[LspMasterORM]:
        """Get LSP master by name.
        
        Args:
            name: LSP name
            session: Optional session
        
        Returns:
            LspMasterORM instance or None if not found
        """
        def _get(sess: Session) -> Optional[LspMasterORM]:
            return sess.query(LspMasterORM).filter_by(name=name).one_or_none()

        if session:
            return _get(session)
        else:
            with self.get_session() as sess:
                return _get(sess)

    def list_lsp_master(
        self, active_only: bool = False, limit: int = None, session: Session = None
    ) -> List[LspMasterORM]:
        """List LSP master records.
        
        Args:
            active_only: If True, only return active LSPs
            limit: Maximum number of records to return
            session: Optional session
        
        Returns:
            List of LspMasterORM instances
        """
        def _list(sess: Session) -> List[LspMasterORM]:
            query = sess.query(LspMasterORM)
            if active_only:
                query = query.filter_by(active=True)
            if limit:
                query = query.limit(limit)
            return query.all()

        if session:
            return _list(session)
        else:
            with self.get_session() as sess:
                return _list(sess)

    def update_lsp_master(
        self, id: int, name: str = None, home_url: str = None, active: bool = None, session: Session = None
    ) -> Optional[LspMasterORM]:
        """Update LSP master record.
        
        Args:
            id: LSP ID
            name: New name (optional)
            home_url: New home URL (optional)
            active: New active status (optional)
            session: Optional session
        
        Returns:
            Updated LspMasterORM instance or None if not found
        """
        def _update(sess: Session) -> Optional[LspMasterORM]:
            lsp = sess.query(LspMasterORM).filter_by(id=id).one_or_none()
            if not lsp:
                return None
            
            if name is not None:
                lsp.name = name
            if home_url is not None:
                lsp.home_url = home_url
            if active is not None:
                lsp.active = active
            
            sess.flush()
            logger.debug("Updated LSP master: id=%s", id)
            return lsp

        if session:
            return _update(session)
        else:
            with self.get_session() as sess:
                return _update(sess)

    def delete_lsp_master(self, id: int, session: Session = None) -> bool:
        """Delete LSP master record.
        
        Args:
            id: LSP ID
            session: Optional session
        
        Returns:
            True if deleted, False if not found
        """
        def _delete(sess: Session) -> bool:
            lsp = sess.query(LspMasterORM).filter_by(id=id).one_or_none()
            if not lsp:
                return False
            sess.delete(lsp)
            sess.flush()
            logger.debug("Deleted LSP master: id=%s", id)
            return True

        if session:
            return _delete(session)
        else:
            with self.get_session() as sess:
                return _delete(sess)

    def upsert_lsp_master(
        self, name: str, home_url: str = None, active: bool = True, lsp_id: int = None, session: Session = None
    ) -> LspMasterORM:
        """Insert or update LSP master record.
        
        Args:
            name: LSP name
            home_url: LSP home URL
            active: Active status
            lsp_id: LSP ID (if updating)
            session: Optional session
        
        Returns:
            LspMasterORM instance (created or updated)
        """
        def _upsert(sess: Session) -> LspMasterORM:
            existing = None
            if lsp_id is not None:
                existing = sess.query(LspMasterORM).filter_by(id=lsp_id).one_or_none()
            else:
                existing = sess.query(LspMasterORM).filter_by(name=name).one_or_none()
            
            if existing:
                existing.name = name
                if home_url is not None:
                    existing.home_url = home_url
                existing.active = active
                sess.flush()
                logger.debug("Updated LSP master: id=%s name=%s", existing.id, name)
                return existing
            else:
                lsp = LspMasterORM(name=name, home_url=home_url, active=active)
                sess.add(lsp)
                sess.flush()
                logger.debug("Created LSP master: id=%s name=%s", lsp.id, name)
                return lsp

        if session:
            return _upsert(session)
        else:
            with self.get_session() as sess:
                return _upsert(sess)

    # ==================== DlgCrawlerConfig CRUD ====================

    def create_dlg_crawler_config(
        self,
        lsp_id: int,
        dlg_url: str,
        is_active: bool = True,
        parse_hint: str = "auto",
        fetch_hint: str = "auto",
        rules_json: Dict = None,
        session: Session = None,
    ) -> DlgCrawlerConfigORM:
        """Create DLG crawler config record.
        
        Args:
            lsp_id: LSP ID (foreign key)
            dlg_url: Disclosure URL
            is_active: Active status
            parse_hint: Parse hint
            fetch_hint: Fetch hint
            rules_json: Rules JSON
            session: Optional session
        
        Returns:
            Created DlgCrawlerConfigORM instance
        """
        def _create(sess: Session) -> DlgCrawlerConfigORM:
            config = DlgCrawlerConfigORM(
                lsp_id=lsp_id,
                dlg_url=dlg_url,
                is_active=is_active,
                parse_hint=parse_hint,
                fetch_hint=fetch_hint,
                rules_json=rules_json,
            )
            sess.add(config)
            sess.flush()
            logger.debug("Created DLG crawler config: lsp_id=%s", lsp_id)
            return config

        if session:
            return _create(session)
        else:
            with self.get_session() as sess:
                return _create(sess)

    def get_dlg_crawler_config(self, lsp_id: int, session: Session = None) -> Optional[DlgCrawlerConfigORM]:
        """Get DLG crawler config by LSP ID.
        
        Args:
            lsp_id: LSP ID
            session: Optional session
        
        Returns:
            DlgCrawlerConfigORM instance or None
        """
        def _get(sess: Session) -> Optional[DlgCrawlerConfigORM]:
            return sess.query(DlgCrawlerConfigORM).filter_by(lsp_id=lsp_id).one_or_none()

        if session:
            return _get(session)
        else:
            with self.get_session() as sess:
                return _get(sess)

    def list_dlg_crawler_config(
        self, active_only: bool = False, limit: int = None, session: Session = None
    ) -> List[DlgCrawlerConfigORM]:
        """List DLG crawler config records.
        
        Args:
            active_only: If True, only return active configs
            limit: Maximum records to return
            session: Optional session
        
        Returns:
            List of DlgCrawlerConfigORM instances
        """
        def _list(sess: Session) -> List[DlgCrawlerConfigORM]:
            query = sess.query(DlgCrawlerConfigORM)
            if active_only:
                query = query.filter_by(is_active=True)
            if limit:
                query = query.limit(limit)
            return query.all()

        if session:
            return _list(session)
        else:
            with self.get_session() as sess:
                return _list(sess)

    def update_dlg_crawler_config(
        self,
        lsp_id: int,
        dlg_url: str = None,
        is_active: bool = None,
        parse_hint: str = None,
        fetch_hint: str = None,
        rules_json: Dict = None,
        session: Session = None,
    ) -> Optional[DlgCrawlerConfigORM]:
        """Update DLG crawler config.
        
        Args:
            lsp_id: LSP ID
            dlg_url: New disclosure URL (optional)
            is_active: New active status (optional)
            parse_hint: New parse hint (optional)
            fetch_hint: New fetch hint (optional)
            rules_json: New rules JSON (optional)
            session: Optional session
        
        Returns:
            Updated DlgCrawlerConfigORM or None if not found
        """
        def _update(sess: Session) -> Optional[DlgCrawlerConfigORM]:
            config = sess.query(DlgCrawlerConfigORM).filter_by(lsp_id=lsp_id).one_or_none()
            if not config:
                return None
            
            if dlg_url is not None:
                config.dlg_url = dlg_url
            if is_active is not None:
                config.is_active = is_active
            if parse_hint is not None:
                config.parse_hint = parse_hint
            if fetch_hint is not None:
                config.fetch_hint = fetch_hint
            if rules_json is not None:
                config.rules_json = rules_json
            
            sess.flush()
            logger.debug("Updated DLG crawler config: lsp_id=%s", lsp_id)
            return config

        if session:
            return _update(session)
        else:
            with self.get_session() as sess:
                return _update(sess)

    def delete_dlg_crawler_config(self, lsp_id: int, session: Session = None) -> bool:
        """Delete DLG crawler config.
        
        Args:
            lsp_id: LSP ID
            session: Optional session
        
        Returns:
            True if deleted, False if not found
        """
        def _delete(sess: Session) -> bool:
            config = sess.query(DlgCrawlerConfigORM).filter_by(lsp_id=lsp_id).one_or_none()
            if not config:
                return False
            sess.delete(config)
            sess.flush()
            logger.debug("Deleted DLG crawler config: lsp_id=%s", lsp_id)
            return True

        if session:
            return _delete(session)
        else:
            with self.get_session() as sess:
                return _delete(sess)

    def upsert_dlg_crawler_config(
        self,
        lsp_id: int,
        dlg_url: str,
        is_active: bool = True,
        parse_hint: str = "auto",
        fetch_hint: str = "auto",
        rules_json: Dict = None,
        session: Session = None,
    ) -> DlgCrawlerConfigORM:
        """Insert or update DLG crawler config.
        
        Args:
            lsp_id: LSP ID
            dlg_url: Disclosure URL
            is_active: Active status
            parse_hint: Parse hint
            fetch_hint: Fetch hint
            rules_json: Rules JSON
            session: Optional session
        
        Returns:
            DlgCrawlerConfigORM instance
        """
        def _upsert(sess: Session) -> DlgCrawlerConfigORM:
            config = sess.query(DlgCrawlerConfigORM).filter_by(lsp_id=lsp_id).one_or_none()
            if config:
                config.dlg_url = dlg_url
                config.is_active = is_active
                config.parse_hint = parse_hint
                config.fetch_hint = fetch_hint
                config.rules_json = rules_json
                sess.flush()
                logger.debug("Updated DLG crawler config: lsp_id=%s", lsp_id)
                return config
            else:
                config = DlgCrawlerConfigORM(
                    lsp_id=lsp_id,
                    dlg_url=dlg_url,
                    is_active=is_active,
                    parse_hint=parse_hint,
                    fetch_hint=fetch_hint,
                    rules_json=rules_json,
                )
                sess.add(config)
                sess.flush()
                logger.debug("Created DLG crawler config: lsp_id=%s", lsp_id)
                return config

        if session:
            return _upsert(session)
        else:
            with self.get_session() as sess:
                return _upsert(sess)

    # ==================== DlgRaw CRUD ====================

    def create_dlg_raw(
        self,
        lsp_id: int,
        lsp_name: str,
        lender: str,
        portfolio: str,
        as_on_timestamp: Any,
        scrape_timestamp: Any,
        amount: float = None,
        complete: str = None,
        session: Session = None,
    ) -> DlgRawORM:
        """Create DLG raw record.
        
        Args:
            lsp_id: LSP ID (part of composite PK)
            lsp_name: LSP name (part of composite PK)
            lender: Lender (part of composite PK)
            portfolio: Portfolio (part of composite PK)
            as_on_timestamp: As-on timestamp (part of composite PK)
            scrape_timestamp: Scrape timestamp (part of composite PK)
            amount: Amount
            complete: Complete flag
            session: Optional session
        
        Returns:
            Created DlgRawORM instance
        """
        def _create(sess: Session) -> DlgRawORM:
            raw = DlgRawORM(
                lsp_id=lsp_id,
                lsp_name=lsp_name,
                lender=lender,
                portfolio=portfolio,
                amount=amount,
                as_on_timestamp=as_on_timestamp,
                scrape_timestamp=scrape_timestamp,
                complete=complete,
            )
            sess.add(raw)
            sess.flush()
            logger.debug("Created DLG raw: lsp_id=%s lender=%s", lsp_id, lender)
            return raw

        if session:
            return _create(session)
        else:
            with self.get_session() as sess:
                return _create(sess)

    def list_dlg_raw(
        self, lsp_id: int = None, lsp_name: str = None, limit: int = None, session: Session = None
    ) -> List[DlgRawORM]:
        """List DLG raw records.
        
        Args:
            lsp_id: Filter by LSP ID (optional)
            lsp_name: Filter by LSP name (optional)
            limit: Maximum records to return
            session: Optional session
        
        Returns:
            List of DlgRawORM instances
        """
        def _list(sess: Session) -> List[DlgRawORM]:
            query = sess.query(DlgRawORM)
            if lsp_id is not None:
                query = query.filter_by(lsp_id=lsp_id)
            if lsp_name is not None:
                query = query.filter_by(lsp_name=lsp_name)
            if limit:
                query = query.limit(limit)
            return query.all()

        if session:
            return _list(session)
        else:
            with self.get_session() as sess:
                return _list(sess)

    def delete_dlg_raw(
        self,
        lsp_id: int,
        lsp_name: str,
        lender: str,
        portfolio: str,
        as_on_timestamp: Any,
        scrape_timestamp: Any,
        session: Session = None,
    ) -> bool:
        """Delete DLG raw record by composite primary key.
        
        Args:
            lsp_id: LSP ID
            lsp_name: LSP name
            lender: Lender
            portfolio: Portfolio
            as_on_timestamp: As-on timestamp
            scrape_timestamp: Scrape timestamp
            session: Optional session
        
        Returns:
            True if deleted, False if not found
        """
        def _delete(sess: Session) -> bool:
            raw = (
                sess.query(DlgRawORM)
                .filter_by(
                    lsp_id=lsp_id,
                    lsp_name=lsp_name,
                    lender=lender,
                    portfolio=portfolio,
                    as_on_timestamp=as_on_timestamp,
                    scrape_timestamp=scrape_timestamp,
                )
                .one_or_none()
            )
            if not raw:
                return False
            sess.delete(raw)
            sess.flush()
            logger.debug("Deleted DLG raw: lsp_id=%s lender=%s", lsp_id, lender)
            return True

        if session:
            return _delete(session)
        else:
            with self.get_session() as sess:
                return _delete(sess)

    # ==================== AuditLog CRUD ====================

    def create_audit_log(
        self,
        action_taken: AuditAction,
        lsp_id: int = None,
        auto_manual: str = None,
        user_id: str = None,
        payload: Dict = None,
        session: Session = None,
    ) -> AuditLogORM:
        """Create audit log record.
        
        Args:
            action_taken: Audit action (required)
            lsp_id: LSP ID (optional)
            auto_manual: Auto/manual flag (optional)
            user_id: User ID (optional)
            payload: Payload JSON (optional)
            session: Optional session
        
        Returns:
            Created AuditLogORM instance
        """
        def _create(sess: Session) -> AuditLogORM:
            audit = AuditLogORM(
                lsp_id=lsp_id,
                auto_manual=auto_manual,
                user_id=user_id,
                payload=payload,
                action_taken=action_taken,
            )
            sess.add(audit)
            sess.flush()
            logger.debug("Created audit log: id=%s action=%s", audit.id, action_taken.value)
            return audit

        if session:
            return _create(session)
        else:
            with self.get_session() as sess:
                return _create(sess)

    def get_audit_log(self, id: int, session: Session = None) -> Optional[AuditLogORM]:
        """Get audit log by ID.
        
        Args:
            id: Audit log ID
            session: Optional session
        
        Returns:
            AuditLogORM instance or None
        """
        def _get(sess: Session) -> Optional[AuditLogORM]:
            return sess.query(AuditLogORM).filter_by(id=id).one_or_none()

        if session:
            return _get(session)
        else:
            with self.get_session() as sess:
                return _get(sess)

    def list_audit_log(
        self, lsp_id: int = None, action: AuditAction = None, limit: int = None, session: Session = None
    ) -> List[AuditLogORM]:
        """List audit log records.
        
        Args:
            lsp_id: Filter by LSP ID (optional)
            action: Filter by action (optional)
            limit: Maximum records to return
            session: Optional session
        
        Returns:
            List of AuditLogORM instances
        """
        def _list(sess: Session) -> List[AuditLogORM]:
            query = sess.query(AuditLogORM)
            if lsp_id is not None:
                query = query.filter_by(lsp_id=lsp_id)
            if action is not None:
                query = query.filter_by(action_taken=action)
            if limit:
                query = query.limit(limit)
            return query.order_by(AuditLogORM.id.desc()).all()

        if session:
            return _list(session)
        else:
            with self.get_session() as sess:
                return _list(sess)

    def delete_audit_log(self, id: int, session: Session = None) -> bool:
        """Delete audit log record.
        
        Args:
            id: Audit log ID
            session: Optional session
        
        Returns:
            True if deleted, False if not found
        """
        def _delete(sess: Session) -> bool:
            audit = sess.query(AuditLogORM).filter_by(id=id).one_or_none()
            if not audit:
                return False
            sess.delete(audit)
            sess.flush()
            logger.debug("Deleted audit log: id=%s", id)
            return True

        if session:
            return _delete(session)
        else:
            with self.get_session() as sess:
                return _delete(sess)


def get_db_manager(db_path: str = None) -> DatabaseManager:
    """Get the singleton DatabaseManager instance.
    
    Args:
        db_path: Path to SQLite database (only used on first call)
    
    Returns:
        Singleton DatabaseManager instance
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(db_path)
        logger.info("Singleton DatabaseManager created")
    return _db_manager


__all__ = ["DatabaseManager", "get_db_manager"]
