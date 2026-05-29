from fraud_lens_gov.sources.compras_gov import ComprasGovClient
from fraud_lens_gov.normalization import from_compras_award


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


def test_compras_csv_award_record_is_enriched_and_normalized():
    client = ComprasGovClient(pncp_client=FakePncpClient())
    record = {
        "id_contratacao_pncp": "33781055000135-1-000463/2026",
        "id_compra_item": "ROW-70",
        "numero_item_pncp": "70",
        "quantidade_homologada": "2",
        "valor_unitario_homologado": "100.50",
        "valor_total_homologado": "201.00",
        "data_resultado_pncp": "2026-05-01T00:00:00",
        "nome_razao_social_fornecedor": "Fornecedor Teste",
        "ni_fornecedor": "123",
        "orgao_entidade_cnpj": "33781055000135",
        "unidade_orgao_codigo_unidade": "999",
    }

    item = from_compras_award(client.enrich_award_record(record))

    assert item.item_description == "PECA EQUIPAMENTO LABORATORIO"
    assert item.unit == "UNIDADE"
    assert item.quantity == 2
    assert item.unit_price == 100.5
    assert item.total_value == 201
