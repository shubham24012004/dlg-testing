from utils.logger_config import logger_method
from typing import List, Optional
from DatabaseOperation.DatabaseModels.orm_models import LspMaster, LspMasterIp
from General.Managers.LspMasterManager import LspMasterManager


class LSPMasterService:
    """Trivial audit logger that writes newline-delimited text files."""

    def __init__(self):
        self.logger = logger_method(__name__)
        self.lsp_manager = LspMasterManager()

    def insert(self, lm: LspMasterIp) -> bool:
        return self.lsp_manager.insert(lm)

    def update(self, lm: LspMaster) -> bool:
        return self.lsp_manager.update(lm)

    def delete(self, lsp_id: int) -> bool:
        return self.lsp_manager.delete(lsp_id)

    def load_active(self) -> List[LspMaster]:
        return self.lsp_manager.load_active()

    def get_lsp_master(self, lsp_id: int) -> Optional[LspMaster]:
        return self.lsp_manager.get_lsp_master(lsp_id)

    def get_lsp_master_by_name(self, name: str) -> Optional[LspMaster]:
        return self.lsp_manager.get_lsp_master_by_name(name)

    def list_lsp_master(
            self, active_only: bool = False, limit: int = None
    ) -> List[LspMaster]:
        return self.lsp_manager.list_lsp_master(active_only, limit)
