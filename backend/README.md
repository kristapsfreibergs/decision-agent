# Decision Agent Backend

Python backend/runtime for the decision harness.

Project shape follows the local template principles:

- `modules/` owns domain logic.
- `shared/` owns infrastructure helpers.
- route/server code stays thin.
- runtime writes go only under `data/`.
- model providers must live behind shared/provider interfaces, not inside modules.

Run from the repository root:

```bash
PYTHONPATH=backend/src python3 -m decision_agent.cli run examples/build-decision-agent.json
PYTHONPATH=backend/src python3 -m decision_agent.server
```

