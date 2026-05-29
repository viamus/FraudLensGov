from __future__ import annotations

from .http import get_json
from ..models import ProcurementItem
from ..normalization import from_pncp_notice


class PncpClient:
    BASE_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
    PROCUREMENT_API_BASE_URL = "https://pncp.gov.br/api/pncp/v1"

    def fetch_contracting_notices(
        self,
        start_date: str,
        end_date: str,
        modality_code: int = 6,
        page_size: int = 10,
        page: int = 1,
        max_pages: int = 1,
    ) -> list[ProcurementItem]:
        records = self.fetch_contracting_notice_records(
            start_date,
            end_date,
            modality_code=modality_code,
            page_size=page_size,
            page=page,
            max_pages=max_pages,
        )
        return [from_pncp_notice(record) for record in records]

    def fetch_contracting_notice_records(
        self,
        start_date: str,
        end_date: str,
        modality_code: int = 6,
        page_size: int = 10,
        page: int = 1,
        max_pages: int = 1,
    ) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for current_page in range(page, page + max(1, max_pages)):
            page_records = self.fetch_contracting_notices_page_raw(
                start_date,
                end_date,
                modality_code=modality_code,
                page_size=page_size,
                page=current_page,
            )
            records.extend(page_records)
            if len(page_records) < page_size:
                break
        return records

    def fetch_contracting_notices_page(
        self,
        start_date: str,
        end_date: str,
        modality_code: int = 6,
        page_size: int = 10,
        page: int = 1,
    ) -> list[ProcurementItem]:
        return [from_pncp_notice(record) for record in self.fetch_contracting_notices_page_raw(
            start_date,
            end_date,
            modality_code=modality_code,
            page_size=page_size,
            page=page,
        )]

    def fetch_contracting_notices_page_raw(
        self,
        start_date: str,
        end_date: str,
        modality_code: int = 6,
        page_size: int = 10,
        page: int = 1,
    ) -> list[dict[str, object]]:
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
        return [record for record in records if isinstance(record, dict)]

    def fetch_procurement_item(
        self,
        cnpj: str,
        year: int,
        sequence: int,
        item_number: int,
    ) -> dict[str, object]:
        return get_json(
            f"{self.PROCUREMENT_API_BASE_URL}/orgaos/{cnpj}/compras/{year}/{sequence}/itens/{item_number}",
            {},
            timeout=45,
            retries=3,
        )
