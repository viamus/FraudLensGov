from __future__ import annotations

from .http import get_json
from ..models import ProcurementItem
from ..normalization import from_pncp_notice


class PncpClient:
    BASE_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"

    def fetch_contracting_notices(
        self,
        start_date: str,
        end_date: str,
        modality_code: int = 6,
        page_size: int = 10,
        page: int = 1,
        max_pages: int = 1,
    ) -> list[ProcurementItem]:
        items: list[ProcurementItem] = []
        for current_page in range(page, page + max(1, max_pages)):
            page_items = self.fetch_contracting_notices_page(
                start_date,
                end_date,
                modality_code=modality_code,
                page_size=page_size,
                page=current_page,
            )
            items.extend(page_items)
            if len(page_items) < page_size:
                break
        return items

    def fetch_contracting_notices_page(
        self,
        start_date: str,
        end_date: str,
        modality_code: int = 6,
        page_size: int = 10,
        page: int = 1,
    ) -> list[ProcurementItem]:
        payload = get_json(
            self.BASE_URL,
            {
                "dataInicial": start_date,
                "dataFinal": end_date,
                "codigoModalidadeContratacao": modality_code,
                "pagina": page,
                "tamanhoPagina": page_size,
            },
            retries=3,
        )
        records = payload.get("data") or []
        return [from_pncp_notice(record) for record in records if isinstance(record, dict)]
