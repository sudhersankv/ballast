# Drop-in data

Put teammate-provided files here as `<set>/<case_id>/{client,holdings,market,events,future}.json` (same schema as `scenarios/cases`).
`python scenarios/generate.py` replaces the generated file with yours, reprices holdings to your market prices, and rescales
history/future if you do not supply them. Re-run `python scenarios/oracle.py` to confirm the case is still solvable.
