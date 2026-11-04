# Political screening analysis

## Files

- `screen_political.py`: pandas-based political candidate screening for `comparia-fr-arena`.
- `political_rules.json`: French/English candidate rules for elections, public policy, immigration, and political figures/parties.
- `build_provisional.py`: builds the ID-only provisional shortlist from the pinned public derivative.
- `requirements.txt`: Python dependencies.
- `../tests/test_screen_political.py`: unit and end-to-end fixture tests.

## Quick start

```bash
python -m pip install -r french-arena/analysis/requirements.txt
python -m unittest discover -s french-arena/tests -v
```

### Full source, default streaming reader

```bash
python french-arena/analysis/screen_political.py \
  --input hf://datasets/ministere-culture/comparia-fr-arena/comparia-fr-arena.parquet \
  --output-dir french-arena/data/full
```

### Exact pandas reader

```bash
python french-arena/analysis/screen_political.py \
  --input hf://datasets/ministere-culture/comparia-fr-arena/comparia-fr-arena.parquet \
  --output-dir french-arena/data/full \
  --direct-pandas
```

This uses:

```python
pd.read_parquet(path, columns=[...])
```

The source file is about 9.5 GB, so direct pandas can require substantial memory. The default reader uses PyArrow/fsspec only to stream batches, then converts each batch to a pandas DataFrame for screening.

### Local Parquet

```bash
python french-arena/analysis/screen_political.py \
  --input /path/to/comparia-fr-arena.parquet \
  --output-dir french-arena/data/full
```

### Useful flags

- `--revision <sha>`: pin a Hugging Face revision.
- `--french-only`: require `metadata.languages` to contain `fr`.
- `--limit-rows N`: partial smoke test only; not a prevalence estimate.
- `--batch-size N`: streaming batch size.
- `--rules path/to/rules.json`: alternate rule file.

## What counts as a candidate?

A conversation is shortlisted if any turn has:

- political text in the user prompt,
- political text in either assistant response, or
- source metadata category `Politics & Government`.

Adjacent categories such as Law & Justice, Society & Social Issues & Human Rights, and Environment do **not** by themselves shortlist a conversation. They are tracked separately in the provisional derivative because the public derivative lacks text for broader screening.

The pipeline exports:

- all turns belonging to shortlisted conversations,
- one sanitized full-conversation row per shortlisted `comparison_id`,
- prompt-level and response-level political flags,
- matched topics and evidence snippets,
- review priority and review status.

## Privacy and safety boundaries

- Do not commit Hugging Face tokens.
- Revoke any token pasted into chat.
- Full raw exports are gitignored by default.
- Hidden `reasoning_content`, system prompts, and tool payloads are excluded from screening and sanitized exports.
- Rule matches are not human-validated labels.

## Rebuild provisional artifacts

If the pinned public derivative is cloned locally:

```bash
git clone https://github.com/simonaszilinskas/style-control-analysis.git /tmp/style-control-analysis
git -C /tmp/style-control-analysis checkout 25a17f883945c2229736bfe17702d966bc94aa0d

python french-arena/analysis/build_provisional.py \
  --reference-dir /tmp/style-control-analysis \
  --output-dir french-arena/data
```

The builder verifies SHA-256 hashes for the two input Parquet files before writing outputs.

## Enrich the provisional CSV with full visible text

The provisional CSV is metadata-only; the screening command above produces a
separate political candidate Parquet and does **not** populate that CSV. To
fetch text for the exact provisional IDs, use an authorized local copy of the
gated source, or configure Hugging Face access locally and use the default
`hf://` source. The pinned provisional source revision is recorded in the CSV
and manifest; use a matching source copy for reliable joins. No source access is
included in this repository.

```bash
python -m pip install -r french-arena/analysis/requirements.txt
python french-arena/analysis/enrich_shortlist.py --input /path/to/comparia-fr-arena.parquet
# Then (re)start python arena/explorer/server.py
```

This writes the separate, gitignored
`french-arena/data/full/political_shortlist_with_text.csv`. Every shortlist ID
is retained, including IDs not found in the source. The highest-turn source
row supplies both complete visible transcripts (including post-vote turns):
JSON arrays preserve each user's and assistant's text separately for both
models. It excludes system, tool, and hidden reasoning fields. Status and
warnings flag missing IDs, missing messages, final-turn/model mismatches,
unequal user prompts and duplicate highest-turn source rows. These are checks,
not proof of completeness; inspect flagged records. No text is fabricated or
truncated. Content blocks are joined with newlines; non-text content is omitted.
Full text may contain sensitive information and should not be committed.
