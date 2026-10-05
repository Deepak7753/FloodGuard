# Dataset files

FloodGuard's training script expects these three INDOFLOODS CSV files in this directory:

- `floodevents_indofloods.csv`
- `precipitation_variables_indofloods.csv`
- `catchment_characteristics_indofloods.csv`

The raw CSV files are intentionally not included in the GitHub-ready package. Before redistributing or committing the dataset, verify the dataset's license and redistribution terms and follow the original provider's citation requirements.

The bundled `model_xgboost_full.pkl` lets the API run without the raw training CSVs.
