# Funder Pitch & Technical Strategy
## Politically Exposed Persons (PEP) Social Intelligence & Verification Pipeline
### Focused Operational Model: Local Ingestion, Human-in-the-Loop Oversight & LLM Grounding

---

### 1. Executive Summary

Electoral commission datasets provide names, wards, and party lists for thousands of political candidates, but **omit their digital identities, official social media pages, and online communication channels**. In an era where political influence, public statements, campaign financing, and conflict-of-interest indicators happen online, tracking candidates' verified digital presence is critical for civic oversight, investigative journalism, and anti-corruption compliance.

This project delivers a **disciplined, cost-efficient, open-source intelligence (OSINT) pipeline** designed for lean operation with full human oversight:
* **Locally Hosted & Contained**: Operates entirely on local workstations with SQLite and static web exports—requiring **$0 cloud hosting costs** and zero enterprise server liabilities.
* **Grounded LLM & Heuristic Evaluation**: Evaluates live Google and Bing search snippets against granular municipal boundaries, party affiliations, and civic roles.
* **Human-in-the-Loop Verification**: Provides researchers with an interactive dashboard featuring municipal context markers, Google Maps boundaries, and one-click verification (`✓` / `✗`).
* **Open Data Interoperability**: Synchronizes in real time with Google Sheets and exports standardized datasets in the international **Popolo Open Data format**.

---

### 2. Strategic Input Filtering & Candidate Prioritization

National candidate lists can exceed 60,000 individuals across municipal, provincial, and national ballots. Rather than querying candidates indiscriminately—which wastes budget on unviable searches—the pipeline applies a **4-tier prioritization funnel**:

```
                       INPUT PRIORITIZATION FUNNEL
                       
 ┌──────────────────────────────────────────────────────────────┐
 │ Raw Candidate Roster (Electoral Commission / IEC Data)       │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                ▼ [5-Tier Input Filtering Hierarchy]
 ┌──────────────────────────────────────────────────────────────┐
 │ Tier 1: Specific Metros / Strategic Geographies              │
 │ Tier 2: National Party Proportional Representation (PR) Lists│
 │ Tier 3: Contested Key Councils & Coalition Swings            │
 │ Tier 4: National Party Ward Candidates                       │
 │ Tier 5: Independents & Micro-Party Candidates                │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
         [ Targeted Dual-Query SERP Search: Google & Bing ]
```

#### Detailed 5-Tier Prioritization Framework

1. **Tier 1 — Specific Metros & Strategic Geographies**:
   * **Scope**: Major metropolitan councils and economic hubs (e.g. City of Johannesburg, Buffalo City, Ekurhuleni, Tshwane, eThekwini, City of Cape Town, Matlosana).
   * **Rationale**: These councils govern the largest public budgets, high-density populations, and major infrastructure portfolios where political accountability and social oversight have the highest national impact.
   * **Search Focus**: Mayoral candidates, executive council members, and high-visibility metro leaders.

2. **Tier 2 — National Party Proportional Representation (PR) Lists**:
   * **Scope**: Top-ranking candidates positioned on national and municipal PR lists across established parliamentary parties (ANC, DA, EFF, ActionSA, IFP, PA, VF Plus, MK).
   * **Rationale**: PR candidates are prioritized by party leadership and are mathematically guaranteed council or legislative seats based on party vote shares, making them high-certainty office holders.

3. **Tier 3 — Contested Key Councils & Coalition Swings**:
   * **Scope**: Highly competitive municipalities and swing districts where no single party holds an absolute majority and coalition governments decide council leadership.
   * **Rationale**: Swing councils represent critical governance flashpoints subject to high public scrutiny, floor-crossing risks, and coalition realignments.

4. **Tier 4 — National Party Ward Candidates**:
   * **Scope**: Direct first-past-the-post ward candidates fielded by major national parties across individual constituencies.
   * **Rationale**: Ward councillors interface directly with grassroots communities and local development projects; national party backing increases the probability of an active campaign and social media footprint.

5. **Tier 5 — Independents & Micro-Party Candidates**:
   * **Scope**: Independent candidates, localized civic associations, and minor unrepresented parties contesting single wards.
   * **Rationale**: Processed after institutional candidates to preserve daily SERP rate-limit quotas, focusing on viable candidates with digital corroboration cues (e.g. verified contact email or civic bio mentions).

---

### 3. Continuous Strengthening of LLM Prompts & Heuristics

The evaluation engine does not treat LLM evaluation as a static prompt. It functions as an **adaptive feedback loop** where every human verification decision actively strengthens the detection heuristics.

```
                    ACTIVE PROMPT STRENGTHENING LOOP
                    
 ┌────────────────────────┐         ┌────────────────────────┐
 │ Search Snippets Ingest │ ──────► │ LLM / Heuristic Engine │
 └────────────────────────┘         └───────────┬────────────┘
                                                │
                                                ▼
 ┌────────────────────────┐         ┌────────────────────────┐
 │ Continuous Rule Tuning │ ◄────── │ Human Review Dashboard │
 │ (Few-shot exemplars,   │  (✓/✗)  │ (1-click verification, │
 │  vernacular lexicon)   │         │  map boundary checks)  │
 └────────────────────────┘         └────────────────────────┘
```

#### Key Dimensions of Prompt & Rubric Strengthening

1. **Active Learning from Human Feedback (`✓` vs `✗`)**:
   * Confirmed true positives (e.g. *Onela Mangxola* in Buffalo City, where the Facebook snippet revealed school details and councillor duties in Bisho) are automatically archived as **few-shot prompt exemplars**.
   * Confirmed false positives (e.g. an individual in London or Nigeria sharing a South African surname) are analyzed to update **negative boundary rules**.
2. **Expansion of the Vernacular & Civic Lexicon**:
   * Candidates frequently campaign in South Africa's official indigenous languages. The evaluation rubric is continuously enriched with multilingual electoral keywords:
     * **isiZulu / isiXhosa**: *ukhetho* (election), *zokhetho* (electoral), *amavoti* (votes), *vota* (vote for), *ikhansela* (councillor).
     * **Afrikaans**: *verkiesing* (election), *stem vir* (vote for), *kandidaat* (candidate), *wyk* (ward).
     * **Sesotho / Setswana**: *dikgetho* / *kgetho* (elections), *mokgethwa* (candidate).
3. **Hardening Against Party Organization Spoilers**:
   * A persistent challenge in political OSINT is distinguishing an individual candidate's profile from an official party branch page (e.g., *"DA Ward 17 Branch"* or *"ANC Youth League Regional Office"* posting a photo of the candidate).
   * The prompt applies strict structural penalties (`-0.50`) to institutional language (*"official page of"*, *"caucus"*, *"parliamentary team"*), ensuring that **only personal or personal-campaign accounts are promoted**.
4. **Dynamic Geographic Triangulation**:
   * Using a curated taxonomy of 23+ municipalities and hundreds of local towns/suburbs, the prompt awards maximum confidence (`+0.30`) to hyper-local suburb mentions (e.g. *Jouberton*, *Kanana*, *Mdantsane*, *Qonce*) rather than broad country-level mentions.

---

### 4. Development Costs & Operational Management Budget

Because this pipeline is locally hosted with human oversight, funders are **not paying for speculative cloud infrastructure, complex Kubernetes clusters, or multi-tenant hosting tiers**. Every dollar goes directly toward data production, algorithmic refinement, and human verification.

#### Budget Model: 6-Month Intensive Operating Window

| Budget Category | Scope & Responsibilities | Effort / Allocation | Monthly Cost | Total (6 Months) |
| :--- | :--- | :--- | :--- | :--- |
| **1. Lead Data Engineer / Pipeline Developer** | System maintenance, SERP parser adjustments, LLM prompt engineering, SQLite database optimization, Google Sheets sync connectors, rate-limit monitors. | ~20 hrs / month ($60/hr) | $1,200 | **$7,200** |
| **2. OSINT Analyst & Verification Specialist** | Daily ingestion runs, triage of prioritized candidate queues, human review of *Potential/Possible* accounts (avg. 15–20 sec/review), geographic corroboration. | ~35 hrs / month ($30/hr) | $1,050 | **$6,300** |
| **3. SERP API Search Queries (Dual-Provider)** | Paced daily search across Google and Bing (1,000 queries/day = 500 candidates/day via Serpent API @ $0.60/1k). Burst failover reserves for sprint weeks. | ~30,000 queries / month | ~$35 | **~$210** |
| **4. LLM Evaluation & Inference Tokens** | Grounded snippet validation, multilingual translation tokens, and prompt scoring passes. | ~100k snippets / month | ~$25 | **~$150** |
| **5. Infrastructure & Tooling** | Local workstation tools, GitHub Pages hosting, domain/security maintenance, SQLite backups. | Flat allocation | $0 (Free tier) | **$0** |
| **TOTAL 6-MONTH PROJECT BUDGET** | | | **~$2,310 / mo** | **~$13,860** |

*Note: For a smaller 3-month pilot (targeting 5,000 key metropolitan candidates), the total budget is approximately **$7,000**.*

---

### 5. Multi-Engine SERP Scaling Strategy

| Provider | Role | Rate Limits & Pacing | Search Engines | Unit Economics |
| :--- | :--- | :--- | :--- | :--- |
| **Serpent API** *(Primary Scheduled Runner)* | Routine daily batching of prioritized queues. | 200 / hr<br>1,000 / day | **Google & Bing (Multi-Engine)** | **$0.60 per 1,000 queries**<br>($0.0012 per candidate for 2 queries). Ingests 500 candidates daily for $0.60/day. |
| **SerpStack / Google Vertex** *(Burst Sprint Option)* | Deployed during critical pre-election weeks when 5,000 candidates must be processed in 24–48 hours. | Unthrottled / Enterprise burst capacity | **Google only** *(Note: Does not index Bing; used for high-speed primary discovery).* | **$1.50 – $4.00 per 1,000 queries**. Bypasses hourly rate limits without IP bans. |

---

### 6. Deliverables & Value to Funder

1. **Verified Digital Registry of South African Leaders**:
   * A comprehensive, audit-certified dataset of thousands of municipal candidates and councillors linked to their verified social media profiles.
2. **Open Data Standard Compliance**:
   * Published as an open **Popolo JSON** dataset, SQLite database, and live Google Sheet accessible to researchers, civil society organizations, and investigative journalists.
3. **Auditable Verification Trail**:
   * Every verified profile is backed by an explicit rationale detailing exact name match tokens, geographic triangulation, party cues, and human verification timestamps.
4. **Reproducible, Open Methodology**:
   * Transparent scoring rubrics and documented algorithmic constraints preventing partisan bias or false-positive hallucinations.
