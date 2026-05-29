from fraud_lens_gov.sources.compras_gov import ComprasGovClient


class FakePncpClient:
    def fetch_procurement_item(self, cnpj: str, year: int, sequence: int, item_number: int):
        assert cnpj == "33781055000135"
        assert year == 2026
        assert sequence == 463
        assert item_number == 70
        return {
            "numeroItem": 70,
            "descricao": "Peca Equipamento Laboratorio",
            "unidadeMedida": "Unidade",
            "catalogoCodigoItem": "ABC123",
            "materialOuServico": "M",
        }


def test_compras_award_record_is_enriched_from_public_pncp_item():
    client = ComprasGovClient(pncp_client=FakePncpClient())
    record = {
        "idContratacaoPNCP": "33781055000135-1-000463/2026",
        "numeroItemPncp": 70,
    }

    enriched = client._enrich_award_record(record)

    assert enriched["descricaoItem"] == "Peca Equipamento Laboratorio"
    assert enriched["unidadeMedida"] == "Unidade"
    assert enriched["catalogoCodigoItem"] == "ABC123"
