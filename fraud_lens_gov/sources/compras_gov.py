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
            timeout=60,
        )
        records = payload.get("resultado") or []
        return [from_compras_award(record) for record in records if isinstance(record, dict)]
