# ESG-Catalyst
An AI-powered ESG reporting and scoring platform. Arabic first / GRI / FRA / SASB 
What does this PR do?



## done
### updated claude.md with session log and obsidian context memory,

### built extractor right to be looking and only relevant chunks instead of full imported PDF ,

### changed router model to a smaller model that pass through the timeout limit,

### added a full M1-M5 pipeline test script

## notes to delve into

### the classification only get the chunks related to the environment because it use climate bert in the NLP extraction and it is not trained well on social and governance wordings so we need to enrich that part

### the metrics schema need immediate update so we can test the extraction more because it only has the main 13 metrics

### test different file types at the ingestion layer (specially tables inside docs - OCR)
