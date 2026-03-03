- Do not use the emailoctopus_db anymore as it is out of date.  This now appears in the .env: MONGODB_OCTOPUS=empower_development
MONGODB_CAMPAIGN=empower_development
- The campaign_data database has been unified into empower_development. The collection `campaign_exposures` is now `exposures`.
- Always consider DRY principles in designing and implementing code.
- Always source venv/bin/activate before running python scripts or tests.

