# Reliability acceptance

Run on a development checkout without production `.env`:

```powershell
$env:HERMES_AGENT_DIR = 'path/to/hermes-agent'
python -m pytest -q evals/reliability_acceptance.py
```

Set `MARK_ACCEPTANCE_REPO` to run the same assertions against another checkout.
The suite forbids network requests, replays a model response, and mocks the paid
actor/Sheet boundary. It measures execution truth, scope, permission and refusal
contracts; it does not measure general live-model factual accuracy.

The exact logged confession is included, with quotation marks around unrelated
phrases. Negative controls keep estimates, unrelated tools and newly blocked
requests from becoming evidence of a completed run.
