from fraud_lens_gov.rag import chunk_text, retrieve_chunks


def test_retrieve_chunks_returns_relevant_document_context():
    chunks = chunk_text(
        document_id="edital-1",
        source="sample",
        text=(
            "O termo de referencia exige notebook corporativo com 16GB de RAM. "
            "A entrega deve ocorrer em ate trinta dias. "
            "O criterio de julgamento sera menor preco por item."
        ),
        chunk_words=8,
        overlap_words=2,
    )

    results = retrieve_chunks("notebook 16GB RAM", chunks)

    assert results
    assert any("notebook" in chunk.text.lower() for chunk, _ in results)
