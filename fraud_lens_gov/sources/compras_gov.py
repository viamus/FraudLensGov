from __future__ import annotations

from .http import get_json
from ..models import ProcurementItem
from ..normalization import from_compras_award


class ComprasGovClient:
    BASE_URL = (
        "https://dadosabertos.compras.gov.br/"
        "modulo-contratacoes/3_consultarResultadoItensContratacoes_PNCP_14133"
    )

    def fetch_awarded_items(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 10,
        page: int = 1,
        max_pages: int = 1,
    ) -> list[ProcurementItem]:
        page_size = max(10, min(page_size, 500))
        items: list[ProcurementItem] = []
        for current_page in range(page, page + max(1, max_pages)):
            page_items = self.fetch_awarded_items_page(
                start_date,
                end_date,
                page_size=page_size,
                page=current_page,
            )
            items.extend(page_items)
            if len(page_items) < page_size:
                break
        return items

    def fetch_awarded_items_page(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 10,
        page: int = 1,
    ) -> list[ProcurementItem]:
        page_size = max(10, min(page_size, 500))
        payload = get_json(
            self.BASE_URL,
            {
                "pagina": page,
                "tamanhoPagina": page_size,
                "dataResultadoPncpInicial": start_date,
                "dataResultadoPncpFinal": end_date,
            },
            timeout=90,
            retries=3,
        )
        records = payload.get("resultado") or []
        return [from_compras_award(record) for record in records if isinstance(record, dict)]
