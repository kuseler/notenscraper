my-scraper-pipeline/
├── .github/
│   └── workflows/
│       └── deploy.yml
├── bootstrap/
│   └── main.tf
├── infra/
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── src/
│   ├── index.py              # Your existing scraper + diff logic
│   └── requirements.txt      # Scraper dependencies (requests, beautifulsoup4, etc.)
└── .gitignore
