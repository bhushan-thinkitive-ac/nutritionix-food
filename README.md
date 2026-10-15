# Nutritionix POC

A Django test harness for the Nutritionix POC brief. It covers NL parsing, calorie accuracy, search relevance, barcode coverage, the voice path, latency and micronutrients.

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install django requests anthropic python-dotenv
cp .env.example .env   # fill NUTRITIONIX_APP_ID / NUTRITIONIX_APP_KEY (+ ANTHROPIC_API_KEY or BEDROCK_AWS_REGION for voice cleanup)
.venv/bin/python manage.py runserver
```
Open http://127.0.0.1:8000. Click **Run all checks** to build the results sheet, then download it with **Download CSV**.
You can also run everything from the CLI: `.venv/bin/python manage.py run_poc`

## Datasets (`poc/data/`)
- `meals.json`: 30 meal texts, with the items each one should parse into and USDA/label reference kcal
- `search_queries.json`: 20 queries (common foods, branded items, misspellings)
- `upcs.json`: 15 slots. Fill these in by scanning physical items: `upc` and `label_kcal`
- `voice_transcripts.json`: 5 transcripts with disfluencies

Results are written to `poc/results/latest.json` and `poc/results/results_sheet.csv`.
