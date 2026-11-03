# evaluation

French Compar:IA arena political-content analysis.

## Deliverables

- Summary and dataset notes: `french-arena/README.md`
- Detailed report: `french-arena/REPORT.md`
- Provisional shortlist: `french-arena/data/political_shortlist_provisional.parquet`
- Pandas screening pipeline: `french-arena/analysis/screen_political.py`
- Tests: `french-arena/tests/test_screen_political.py`

## Status

The full gated Hugging Face source could not be read from this sandbox. A provisional ID-only shortlist was built from a pinned public derivative of `ministere-culture/comparia-fr-arena`.

Provisional headline: **8,739 conversations** with source primary topic `Politics & Government`, out of **137,293** derived French conversations with a decisive vote (**6.37%**). These are review candidates, not manually validated political labels.

## Run tests

```bash
python -m pip install -r french-arena/analysis/requirements.txt
python -m unittest discover -s french-arena/tests -v
```

## Screen the full source

```bash
python french-arena/analysis/screen_political.py \
  --input hf://datasets/ministere-culture/comparia-fr-arena/comparia-fr-arena.parquet \
  --output-dir french-arena/data/full
```

Use `--direct-pandas` for the exact `pd.read_parquet(...)` reader. Full raw exports are gitignored by default.
