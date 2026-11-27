# Histology WSI Agentic Analyzer

An agentic AI pipeline for histology whole-slide image (WSI) analysis in
pharmaceutical R&D — built as a portfolio project for a Merck Senior AI
Data Scientist application (agentic generative AI, computer vision,
histology, gigapixel whole-slide images, applied statistics).

**All data is synthetic and seeded.** No real slides, patients, tissue,
or Merck data is used. No model weights or API calls: the feature
extractor is a deterministic stand-in with the same interface a vision
foundation model would plug into (`extract_features(tile)` returns a
fixed-length vector). This is a demo of the pipeline architecture, the
agentic workflow, and the statistics — not a claim of real histology
research or a production vision system.

## The problem

A gigapixel whole-slide image cannot be fed to a model whole: it must be
tiled, cleaned, and summarised, and an agentic system that drafts
findings from those tiles can state numbers it never computed. This
pipeline does the full loop honestly: preprocessing with QC, feature
extraction, per-slide summaries, a treated-vs-control comparison with
real statistics, and a reviewer that rejects any claim whose numbers
are not in the computed results. Nothing is released without a human
approval gate.

## What it does

- **Synthetic slides** (`wsi_agent/data.py`) — seeded slide grids
  (16×16 tiles of 512px), tissue flags, stain vectors, nuclei counts;
  a two-arm study (treated vs control) with a real seeded difference.
- **Preprocessing** (`wsi_agent/preprocess.py`) — tissue detection,
  stain normalisation to a reference, QC that rejects out-of-focus,
  empty, or stain-outlier tiles with a reason for each rejection.
- **Features** (`wsi_agent/features.py`) — deterministic 6-feature tile
  vectors and slide-level embeddings; a vision foundation model plugs
  into the same `extract_features()` interface.
- **Agentic workflow** (`wsi_agent/agent.py`) — planner, preprocessor,
  analyst, and reviewer agents; every tool call is traced (tool, args,
  latency, outcome). The reviewer rejects ungrounded claims; the final
  report releases only after human approval.
- **Statistics** (`wsi_agent/stats.py`) — Wilson intervals, Welch's
  t-test and Cohen's d, implemented from scratch (standard library only).
- **Evaluation** (`wsi_agent/evaluate.py`) — reproducibility (same seed,
  same result), groundedness, QC sanity, and the approval gate.
- **Protocol + report** (`wsi_agent/report.py`) — a formal analytic
  protocol authored before analysis, and a plain-language findings report.

## Run it

```bash
python run_analysis.py            # findings held for human review
python run_analysis.py --approve  # human approval gate: release findings
python -m pytest -q               # tests
```

Demo run (seeded study, 12 slides): treated mean tile score 0.731 vs
control 0.662, Welch t=4.029, p=0.0001, Cohen's d=2.326; all 4 drafted
claims kept after review, 0 rejected. See `outputs/` after a run.

## Skills used

Only skills Dharma has verified: Python, statistics, data validation,
PyTest, Git. No histology, computer-vision, or foundation-model
production experience is claimed — the vision-model interface is a
documented stand-in, and the histology domain gap is flagged honestly
in the application notes.
