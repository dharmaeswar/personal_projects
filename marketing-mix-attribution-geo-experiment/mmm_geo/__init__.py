"""Marketing mix modeling, attribution and geo-experiment incrementality.

Synthetic-data demo built for a Data Scientist, Marketing application:
- MMM with geometric adstock + Hill saturation, fit by Ridge regression.
- Multi-touch attribution: last-touch, first-touch, position-based, Shapley.
- Geo holdout experiment: difference-in-differences with CUPED adjustment.
All data is synthetic (seeded); nothing here claims production marketing data.
"""

__all__ = ["data_gen", "mmm", "attribution", "geo_experiment", "report"]
