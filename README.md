# FraudLensGov

FraudLensGov is an open-source project for reading public procurement and bidding data, organizing it into auditable signals, and using ChatGPT-assisted analysis to highlight potential fraud-risk patterns.

The goal is to support transparency, investigative triage, and public-interest oversight. The project is not meant to accuse people or organizations automatically; it should surface explainable indicators that can be reviewed by humans with the proper context.

## What This Project Will Do

- Ingest data from public procurement APIs and open government portals.
- Normalize bidding, supplier, contract, agency, and timeline data.
- Detect suspicious patterns such as repeated winners, unusual price deltas, fragmented purchases, supplier clustering, and deadline anomalies.
- Use ChatGPT to generate structured, explainable risk analysis from the collected evidence.
- Produce transparent reports with sources, reasoning, confidence levels, and review notes.

## Early Technical Direction

The initial implementation will likely use Python because it is a strong fit for API ingestion, data processing, anomaly detection, and AI-assisted analysis.

Possible stack:

- Python for ingestion, enrichment, and risk analysis.
- FastAPI or a CLI for the first usable interface.
- PostgreSQL or DuckDB for structured storage and analytical queries.
- OpenAI API for explainable language-model analysis.
- Docker for reproducible local execution.

## Guiding Principles

- **Evidence first:** every insight should trace back to source data.
- **Human review required:** the system flags risk signals, not final legal conclusions.
- **Transparency by design:** prompts, rules, thresholds, and assumptions should be inspectable.
- **Public-good orientation:** the project should help auditors, journalists, civic technologists, and researchers work faster and more responsibly.

## Status

This repository is in the planning and early bootstrap stage.

## License

License to be defined.
