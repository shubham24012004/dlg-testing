from utils.logger_config import logger_method
from typing import Optional, Any
from DatabaseOperation.DatabaseModels.orm_models import LspMaster, LspMasterIp
from General.Managers.LspMasterManager import LspMasterManager


class LSPMasterService:
    """Trivial audit logger that writes newline-delimited text files."""

    def __init__(self):
        self.logger = logger_method(__name__)
        self.lsp_manager = LspMasterManager()

    def insert(self, lm: LspMasterIp) -> Any:
        master_obj = LspMaster()
        master_obj.home_url = lm.lsp_home_url
        master_obj.name = lm.lsp_name
        master_obj.dlg_url = self.find_dlg_url(lm.lsp_home_url)
        master_obj.active = True
        master_obj.parse_hint = 'auto'
        master_obj.fetch_hint = 'auto'
        master_obj.rules_json = '{}'
        # todo add audit log here
        return self.lsp_manager.insert(master_obj)

    def update(self, lm: LspMaster) -> LspMaster | None:
        # todo add audit log here
        return self.lsp_manager.update(lm)

    def delete(self, lsp_id: int) -> int:
        # todo add audit log here
        return self.lsp_manager.delete(lsp_id)

    @staticmethod
    def find_dlg_url(lsp_home_url) -> str | None:
        # todo: write code for DLG url finder here and update lsp master with value of URL found/None
        return None

    def load_active(self, lsp_id: Optional[int] = None) -> tuple[list[dict[Any, Any] | dict[str, Any] | dict[str, str]], Any]:
        return self.list_lsp_master(active_only=True, lsp_id=lsp_id)

    def list_lsp_master(
            self, active_only: bool = False, per_page: int = None, page: int = None,  lsp_id: int = None, lsp_name: str = None
    ) -> tuple[list[dict[Any, Any] | dict[str, Any] | dict[str, str]], Any]:

        return self.lsp_manager.list_lsp_master(active_only, per_page, page, lsp_id, lsp_name)
