# Sample data

Drop the real supplied `orders.csv` and `payments.csv` in this folder
(`backend/sample_data/orders.csv`, `backend/sample_data/payments.csv`) if
you have them -- the `POST /datasets/demo` endpoint reads them directly and
runs them through the exact same ingestion/reconciliation pipeline as a
normal upload.

No such files were supplied with this assignment, so `orders.csv` and
`payments.csv` in this folder are **synthetic data generated for this
project** (see `generate_sample_data.py`), not real business data. They
exist so the "Load Demo Data" button and the reconciliation engine have
something deterministic to run against end-to-end, and so the automated
tests have a realistic-shaped fixture. Replace them with real files at any
time -- nothing else needs to change.
