from __future__ import annotations

from .http import get_json
from .pncp import PncpClient
from ..models import ProcurementItem
from ..normalization import from_compras_award


class ComprasGovClient:
    BASE_URL = (
        "https://dadosabertos.compras.gov.br/"
        "modulo-contratacoes/3_consultarResultadoItensContratacoes_PNCP_14133"
    )

    def __init__(self, pncp_client: PncpClient | None = None):
        self.pncp_client = pncp_client or PncpClient()

    def fetch_awarded_items(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 10,
        page: int = 1,
        max_pages: int = 1,
    ) -> list[ProcurementItem]:
        page_size = max(10, min(page_size, 500))
        records = self.fetch_awarded_item_records(
            start_date,
            end_date,
            page_size=page_size,
            page=page,
            max_pages=max_pages,
        )
        enriched_records = [self.enrich_award_record(record) for record in records]
        return [from_compras_award(record) for record in enriched_records]

    def fetch_awarded_item_records(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 10,
        page: int = 1,
        max_pages: int = 1,
    ) -> list[dict[str, object]]:
        page_size = max(10, min(page_size, 500))
        records: list[dict[str, object]] = []
        for current_page in range(page, page + max(1, max_pages)):
            page_records = self.fetch_awarded_items_page_raw(
                start_date,
                end_date,
                page_size=page_size,
                page=current_page,
            )
            records.extend(page_records)
            if len(page_records) < page_size:
                break
        return records

    def fetch_awarded_items_page(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 10,
        page: int = 1,
    ) -> list[ProcurementItem]:
        records = self.fetch_awarded_items_page_raw(start_date, end_date, page_size=page_size, page=page)
        enriched_records = [self.enrich_award_record(record) for record in records]
        return [from_compras_award(record) for record in enriched_records]

    def fetch_awarded_items_page_raw(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 10,
        page: int = 1,
    ) -> list[dict[str, object]]:
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
        return [record for record in records if isinstance(record, dict)]

    def enrich_award_record(self, record: dict[str, object]) -> dict[str, object]:
        if record.get("descricaoItem"):
            return record
        cnpj, year, sequence = _parse_pncp_control(str(record.get("idContratacaoPNCP") or ""))
        item_number = record.get("numeroItemPncp")
        if not cnpj or not year or not sequence or not item_number:
            return record
        try:
            item_detail = self.pncp_client.fetch_procurement_item(cnpj, year, sequence, int(item_number))
        except Exception as exc:
            enriched = dict(record)
            enriched["descricaoItemEnrichmentError"] = str(exc)
            return enriched
        enriched = dict(record)
        enriched["descricaoItem"] = item_detail.get("descricao") or record.get("descricaoItem")
        enriched["unidadeMedida"] = item_detail.get("unidadeMedida") or record.get("unidadeMedida")
        enriched["catalogoCodigoItem"] = item_detail.get("catalogoCodigoItem")
        enriched["materialOuServico"] = item_detail.get("materialOuServico")
        enriched["pncpItemDetail"] = item_detail
        return enriched

    def _enrich_award_record(self, record: dict[str, object]) -> dict[str, object]:
        return self.enrich_award_record(record)


def _parse_pncp_control(value: str) -> tuple[str, int | None, int | None]:
    # Expected format: CNPJ-1-000463/2026.
    if not value or "/" not in value:
        return "", None, None
    prefix, year_text = value.rsplit("/", 1)
    parts = prefix.split("-")
    if len(parts) < 3:
        return "", None, None
    cnpj = parts[0]
    sequence_text = parts[-1]
    try:
        return cnpj, int(year_text), int(sequence_text)
    except ValueError:
        return "", None, None
