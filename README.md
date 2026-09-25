# PEP Social Intelligence & Popolo Civic Pipeline 🇿🇦

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Popolo Compliant](https://img.shields.io/badge/Standard-Popolo%20Civic%20Data-emerald.svg)](http://www.popoloproject.com/)
[![SQLite WebAssembly](https://img.shields.io/badge/Database-SQLite%203%20WASM-orange.svg)](https://sql.js.org/)
[![GitHub Pages](https://img.shields.io/badge/Deployment-GitHub%20Pages%20Ready-purple.svg)](docs/)

An automated OSINT discovery, verification, and standardization pipeline for Politically Exposed Persons (PEPs) and South African Local Government Election Candidates. The pipeline discovers candidate social media profiles (LinkedIn, Facebook, Instagram, YouTube, TikTok, X/Twitter), performs deep profile page verification, and exports results into a **Popolo-compliant SQLite database** and a **standalone static web application** ready for GitHub Pages.

---

## 🌟 Key Features

- **Standalone Static Dashboard (`docs/`)**: 100% serverless single-page app ready to host on GitHub Pages.
- **Embedded SQLite WebAssembly Engine**: Run real SQL queries (`SELECT ... WHERE ...`) directly inside the visitor's browser against the bundled `peps.db` file using `sql.js`.
- **Complete Dataset Downloads**: Direct 1-click downloads for both `data/peps.db` (SQLite) and `data/popolo_sa_candidates.json` (Popolo format).
- **Two-Stage Profile Verification**:
  1. *Preview Evaluation*: Multi-permutation name matching, district/municipal cluster expansion, and party account disqualification.
  2. *Deep Profile Inspection*: For matches scoring $\ge 0.50$, fetches live profile metadata to verify political party affiliations, biographical details, municipal council/councillor positions, and recent post context.
- **Exhaustive Name Permutations**: Resolves all realistic registration patterns: *First Last*, *Last First*, *Middle Last*, *Last Middle*, *First Middle*, and full 3-name variants.
- **Daily Budget Hard-Stop**: Automatically stops and saves progress upon reaching a configurable daily query ceiling (default: 1,000 queries/day) with disk-backed response caching.

---

## 📊 Live Discovery Statistics

| Metric | Status |
| :--- | :--- |
| **Total Candidates Ingested** | **1,301** |
| **Candidates with Discovered Accounts** | **709** (54.5% hit rate) |
| **Total Discovered Social Accounts** | **3,002** |
| **High Confidence Matches ($\ge 0.70$)** | **1,101** |
| **Medium Confidence Matches ($0.40 - 0.69$)** | **1,728** |
| **SQLite Database Size** | **4.6 MB** (`peps.db`) |
| **Popolo Collection JSON Size** | **1.5 MB** (`popolo_sa_candidates.json`) |

### Platform Distribution
- **Facebook**: 1,337 accounts (vanity and `/p/<name>-<id>` direct profiles)
- **LinkedIn**: 840 accounts (biographies, municipal roles, education)
- **Instagram**: 333 accounts
- **YouTube**: 303 channels and campaign videos
- **Candidate Web**: 78 verified portals
- **TikTok**: 75 handles
- **Twitter / X**: 36 handles

---

## 🚀 Quick Start: Deploying to GitHub Pages

The static website is pre-built in the [`docs/`](docs/) directory and contains the application, SQLite database, and JSON search index.

1. **Push to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: PEP social intelligence pipeline & static dashboard"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo-name>.git
   git push -u origin main
   ```

2. **Enable GitHub Pages**:
   - Go to your repository on GitHub.
   - Navigate to **Settings** $\rightarrow$ **Pages** (under "Code and automation").
   - Under **Build and deployment** $\rightarrow$ **Source**, choose **Deploy from a branch**.
   - Under **Branch**, select `main` and choose folder **`/docs`**.
   - Click **Save**.

Your static dashboard will be live at:
```
https://<your-username>.github.io/<your-repo-name>/
```

---

## 💻 Running the Discovery Pipeline Locally

### 1. Requirements & Setup
```bash
# Clone the repository
git clone https://github.com/<your-username>/<your-repo-name>.git
cd <your-repo-name>

# Install Python dependencies
pip install -r requirements.txt

# Configure your Serper Google Search API key
cp .env.example .env
# Edit .env and insert your SERPER_API_KEY
```

### 2. Execution Examples

#### Run candidates assigned to a specific researcher:
```bash
python3 run_pipeline.py --researcher "Andrew Fraser" --start-id pers_18589 --limit 200
```

#### Run candidates by index slice:
```bash
python3 run_pipeline.py --start 0 --limit 100
```

#### Run specific candidate IDs:
```bash
python3 run_pipeline.py --ids pers_18589,pers_18590,pers_18591
```

### 3. Rebuilding the Static Site & Database Export
After running new candidate discovery batches, re-export the static site bundle:
```bash
python3 build_static_site.py
```
This updates:
- `docs/index.html`
- `docs/data/peps.db`
- `docs/data/candidates.json`
- `docs/data/stats.json`
- `docs/data/popolo_sa_candidates.json`

---

## 🏛️ Popolo Specification Compliance

All candidates and social media accounts adhere to the [Popolo Project Civic Data Standard](http://www.popoloproject.com/).

### Popolo JSON Representation
```json
{
  "id": "pers_18591",
  "name": "MOKGWAABONE DAVID SHOMANG",
  "given_name": "MOKGWAABONE",
  "additional_name": "DAVID",
  "family_name": "SHOMANG",
  "party_name": "Patriotic Alliance",
  "office": "Ward Candidate",
  "district": "NW403 - Matlosana",
  "links": [
    {
      "url": "https://za.linkedin.com/in/david-shomang-09001a17a",
      "note": "LinkedIn Profile (Confidence: 1.0 - HIGH)"
    }
  ],
  "contact_details": [
    {
      "type": "linkedin",
      "value": "https://za.linkedin.com/in/david-shomang-09001a17a",
      "label": "David Shomang",
      "confidence": 1.0,
      "confidence_level": "HIGH",
      "rationale": "Target: 'MOKGWAABONE DAVID SHOMANG' in 'NW403 - Matlosana'. Match score: 1.0. Title: 'DAVID SHOMANG - Managing Director at SARSCOM - LinkedIn'.",
      "signals": [
        "MIDDLE_LAST_EXACT_MATCH (david shomang)",
        "LOCATION_MATCH (south africa)",
        "DIRECT_PROFILE_URL",
        "BIO_CONTEXT_MATCH (director)"
      ]
    }
  ]
}
```

---

## 🗄️ SQLite Database Schema (`peps.db`)

### `persons`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `TEXT PRIMARY KEY` | Unique Candidate ID (e.g. `pers_18589`) |
| `name` | `TEXT NOT NULL` | Full Name |
| `first_name` | `TEXT` | Given name |
| `middle_name` | `TEXT` | Middle name(s) |
| `last_name` | `TEXT` | Surname / Family name |
| `party_name` | `TEXT` | Political party name |
| `office` | `TEXT` | Electoral candidacy role / office |
| `district` | `TEXT` | Electoral district / municipality |
| `popolo_json` | `TEXT` | Full Popolo JSON string |
| `created_at` | `TIMESTAMP` | Record creation timestamp |

### `social_accounts`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `INTEGER PRIMARY KEY` | Auto-increment identifier |
| `person_id` | `TEXT NOT NULL` | Foreign key referencing `persons(id)` |
| `platform` | `TEXT NOT NULL` | `linkedin`, `facebook`, `instagram`, `youtube`, `tiktok`, `twitter` |
| `profile_url` | `TEXT NOT NULL` | Validated profile URL |
| `label` | `TEXT` | Account display name |
| `confidence` | `REAL NOT NULL` | Confidence score ($0.0 - 1.0$) |
| `confidence_level` | `TEXT NOT NULL` | `HIGH`, `MEDIUM`, `LOW` |
| `rationale` | `TEXT` | Evaluation rationale |
| `signals` | `TEXT` | JSON list of triggered verification signals |
| `created_at` | `TIMESTAMP` | Timestamp |

---

## 📖 Methodology & Research Limitations

A comprehensive, transparent explainer of the discovery workflow, confidence scoring matrix, and research limitations is available in the web dashboard and documented in [`docs/methodology.html`](docs/methodology.html).

### Critical Operational Limitations:
1. **Private & Friends-Only Accounts**: Candidates whose profiles are set to private (e.g. friends-only on Facebook or private Instagram) are invisible to search engines and automated scrapers.
2. **Unindexed Pages**: Recently created campaign accounts or profiles with `noindex` directives cannot be indexed by search engine spiders.
3. **Platform Walled Gardens**: Social networks (especially LinkedIn, Facebook, Instagram) enforce authentication barriers and login redirects for unauthenticated visitors.
4. **CAPTCHAs & Bot Mitigation**: Automated deep verification can encounter Cloudflare Turnstile, reCAPTCHA, or DataDome challenges requiring human verification.
5. **LLM & Heuristic Scoring Constraints**: Scoring relies on textual bio and title cues; ambiguous wording, homonyms, or scarce biographies may elude automated detection.
6. **Prevalent Names & Demographic Clustering**: Common patronyms and clan names (*e.g.* Dlamini, Khumalo, Ndlovu, Mkhize, Botha, Van der Merwe) are shared by many individuals in the same municipality; manual human cross-referencing is essential before asserting identity.

---

## 📜 License & Attribution

- **Code License**: [MIT License](LICENSE)
- **Data Standard**: [Popolo International Civic Data Specification](http://www.popoloproject.com/)
- **Methodology Explainer**: [docs/methodology.html](docs/methodology.html)
- **Original Candidate Source**: South Africa Local Government Election Candidate Lists.
