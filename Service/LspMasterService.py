from utils.logger_config import logger_method
from typing import Optional, Any, List, Dict
from DatabaseOperation.DatabaseModels.master_models import LspMaster, LspMasterIp
from utils.constants import AuditAction
from Managers.LspMasterManager import LspMasterManager
from Service.AuditLogService import AuditLogService
from Service.DisclosureUrlFinderService import DisclosureUrlFinderService


class LSPMasterService:
    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.logger = logger_method(__name__)
        self.user_claims = user_claims
        self.lsp_manager = LspMasterManager(user_claims)
        self.auditlog_service = AuditLogService(user_claims)
        self.disclosure_url_service = DisclosureUrlFinderService(user_claims)

    def insert(self, lm: LspMasterIp) -> Any:
        try:
            master_obj = LspMaster()
            master_obj.home_url = lm.lsp_home_url
            master_obj.name = lm.lsp_name
            master_obj.brand_name = lm.brand_name if lm.brand_name is not None else lm.lsp_name
            master_obj.lsp_type = lm.lsp_type
            master_obj.dlg_url = None
            master_obj.active = True
            master_obj.parse_hint = 'auto'
            master_obj.fetch_hint = 'auto'
            master_obj.rules_json = '{}'
            result = self.lsp_manager.insert(master_obj)
            if not result:
                raise Exception("LSP already exists")

            user_id = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=result["id"],
                    action_taken=AuditAction.INSERT_LSP,
                    auto_manual="auto",
                    user_id=user_id,
                    payload={"status": "Success", "details": f"Added New LSP", "request_object": result}
                )
            )
            return result
        except Exception as ex:
            user_id = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=None,
                    action_taken=AuditAction.INSERT_LSP,
                    auto_manual="auto",
                    user_id=user_id,
                    payload={"status": "Exception", "details": f"{str(ex)}", "request_object": lm.__dict__}
                )
            )
            raise ex

    def update(self, lm: LspMaster) -> LspMaster | None:
        try:
            result = self.lsp_manager.update(lm)
            if not result:
                raise Exception("LSP not found")
            
            user_id = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=lm.id,
                    action_taken=AuditAction.UPDATE_LSP,
                    auto_manual="auto",
                    user_id=user_id,
                    payload={"status": "Success", "details": f"Updated LSP", "request_object": result},
                )
            )
            return result
        except Exception as ex:
            input_obj = lm.__dict__
            del input_obj['_sa_instance_state']
            print(input_obj)
            user_id = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=lm.id,
                    action_taken=AuditAction.UPDATE_LSP,
                    auto_manual="auto",
                    user_id=user_id,
                    payload={"status": "Exception", "details": f"{str(ex)}", "request_object": input_obj}
                )
            )
            raise ex

    def delete(self, lsp_id: int) -> int:
        try:
            result = self.lsp_manager.delete(lsp_id)
            if result <= 0:
                raise Exception("LSP not found")

            user_id = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=str(lsp_id),
                    action_taken=AuditAction.DELETE_LSP,
                    auto_manual="auto",
                    user_id=user_id,
                    payload={"status": "Success", "details": f"Deleted LSP", "request_object": result}
                )
            )
            return result
        except Exception as ex:
            user_id = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=str(lsp_id),
                    action_taken=AuditAction.DELETE_LSP,
                    auto_manual="auto",
                    user_id=user_id,
                    payload={"status": "Exception", "details": f"{str(ex)}", "request_object": str(lsp_id)}
                )
            )
            raise ex

    def find_dlg_url(self, home_url):
        dlg_url = None
        reason = None
        lsp_name = ""
        try:
            dlg_url, reason = self.disclosure_url_service.find_dlg_disclosure_url(home_url)
        except Exception as ex:
            user_id = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=None,
                    action_taken=AuditAction.URL_FINDER,
                    auto_manual="auto",
                    user_id=user_id,
                    payload={"status": "Exception", "details": f"{str(ex)} reason: {reason}",
                             "request_object": f'lsp_id: {lsp_id}'}
                )
            )
        user_id = self.user_claims.get('username') if self.user_claims else "system"
        self.auditlog_service.record(
            self.auditlog_service.build(
                lsp_id=None,
                action_taken=AuditAction.URL_FINDER,
                auto_manual="auto",
                user_id=user_id,
                payload={"status": "Success",
                         "details": {"home_url": home_url, "dlg_url": dlg_url, "reason": reason},
                         "request_object": f'home_url: {home_url}'}
            )
        )
        return dlg_url, reason

    def load_active(self, lsp_id: Optional[int] = None) -> List[LspMaster]:
        result, total_count, rows = self.list_lsp_master(active_only=True, lsp_id=lsp_id, per_page=None)
        lsp_master_list = []
        for row in result:
            lsp_master_obj = LspMaster(**row)
            lsp_master_list.append(lsp_master_obj)
        return lsp_master_list

    def list_lsp_master(
            self, active_only: bool = False, per_page: int = 10, page: int = 1, lsp_id: int = None,
            lsp_name: str = None, lsp_type: str = None
    ) -> tuple[list[dict[Any, Any] | dict[str, Any] | dict[str, str]], Any, Any]:

        return self.lsp_manager.list_lsp_master(active_only, per_page, page, lsp_id, lsp_name, lsp_type)
