# Implementation Plan: Option A (Locally Controlled OSINT Pipeline with Remote Verification & Audit Ledger)

**Project**: Politically Exposed Persons (PEP) Social Intelligence & Verification Pipeline  
**Deployment Model**: Option A — Lean Local Search Pipeline with Human Oversight & Distributed Remote Verifiers  
**Target Region**: South Africa (Municipal, Metro & Ward Candidates)  
**Standard**: Popolo Open Data Specification, SQLite SSOT, Full Verification Audit Ledger  

---

## 1. Executive Strategy & Architectural Principles

Option A delivers an institutional-grade, auditable research pipeline without speculative cloud infrastructure costs or multi-tenant complexity. The core architecture balances **automated discovery** (via dual-engine SERP searches and grounded LLM scoring) with **human-in-the-loop remote verification**, governed by a strict **Single Point of Truth (SSOT)** and an **immutable audit ledger**.

```
                        OPTION A ARCHITECTURAL OVERVIEW
                        
   ┌─────────────────────────────────────────────────────────────────┐
   │                IEC Candidate Roster (3,797+ records)            │
   └────────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │         5-Tier Input Filtering & Prioritization Engine           │
   │  (Tier 1 Metros ➔ Tier 2 PR Lists ➔ Tier 3 Key Councils ➔ etc.) │
   └────────────────────────────────┬────────────────────────────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
      [Serpent API (Google & Bing)]        [Burst Failover: Google Only]
      (Routine Paced: 200/hr, 1k/day)      (SerpStack / Vertex AI Sprint)
                  │                                   │
                  └─────────────────┬─────────────────┘
                                    │
                                    ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │       Grounded LLM Evaluator & Geographic Triangulation         │
   │      (Confidence Scoring: 0.00 - 1.00 + Explicit Evidence)      │
   └────────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │           Single Point of Truth Database: SQLite / libSQL       │
   │        • Candidates (Popolo)     • Social Accounts              │
   │        • Append-Only Audit Log   • Reversible State Machine     │
   └────────────────────────────────┬────────────────────────────────┘
                     ▲                             ▲
                     │ (Local sync / tunnel)       │ (Audit ledger updates)
   ┌─────────────────┴─────────────┐ ┌─────────────┴─────────────────┐
   │ Local Engineer Workstation    │ │ Remote Verifiers (Web UI)     │
   │ • Query builder & crawler     │ │ • Authenticated reviewer ID   │
   │ • Prompt optimization engine  │ │ • Instant 1-click verify      │
   │ • Google Sheets / JSON export │ │ • Full 1-click reversibility  │
   └───────────────────────────────┘ └───────────────────────────────┘
```

---

## 2. Key Pillars: SSOT, Remote Verifiers, Audit Trail & Reversibility

### 2.1 Single Point of Truth (SSOT)
To eliminate "split-brain" discrepancies where search workers, local databases, and remote verifiers hold conflicting statuses:
* **Canonical Core**: `peps.db` (or libSQL/Turso replica) serves as the sole authoritative repository.
* **Direct Real-Time Access**: Remote verifiers interact with the lightweight Python REST backend (`app.py`), either over a secure encrypted tunnel (ngrok / Tailscale Funnel) or via a free-tier Turso libSQL sync.
* **Offline Fallback with Dirty-Bit Syncing**: If remote verifiers access the GitHub Pages static export, local changes are cached with a hash and synchronized back to the primary SQLite database upon reconnection.

### 2.2 Remote Verifiers & Session Attribution
* Remote researchers and OSINT analysts are provisioned with unique Verifier Handles (`verifier_id`, e.g., `analyst_sipho`, `lead_sarah`).
* Every verification action (`confirm`, `reject`, `flag_disputed`, `revert`) requires this handle, preventing anonymous state modifications.

### 2.3 Immutable Audit Ledger (`verification_audit_log`)
Direct overwriting of verification fields is prohibited. All actions append a row to `verification_audit_log`:

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Sequential audit transaction ID |
| `account_id` | INTEGER | Foreign key referencing `social_accounts.id` |
| `person_id` | TEXT | Candidate identifier (e.g. `ZA-MNG-0012`) |
| `profile_url` | TEXT | Target social media URL |
| `verifier_id` | TEXT | Identity handle of the verifier |
| `action` | TEXT | Action type: `VERIFY_CONFIRM`, `VERIFY_REJECT`, `REVERT_ACTION` |
| `previous_status`| TEXT | Status prior to action (`unverified`, `confirmed`, `rejected`) |
| `new_status` | TEXT | Applied status (`confirmed`, `rejected`, `unverified`) |
| `notes` | TEXT | Verifier justification (e.g., *"Photo matches IEC ballot poster"*) |
| `created_at` | TIMESTAMP | ISO 8601 UTC timestamp of the action |

### 2.4 1-Click Reversibility (Rollback State Machine)
* Any erroneous or disputed verification can be reverted instantly.
* Reverting does not delete history: it appends a `REVERT_ACTION` entry pointing to the prior log ID and restores `social_accounts.human_verification` to the exact state before the mistake was made.

---

## 3. Work Breakdown Structure (WBS) & Implementation Phases

The rollout is structured into **four 2-week execution sprints (8 weeks total)**, transitioning seamlessly into ongoing operations:

```
                      8-WEEK IMPLEMENTATION TIMELINE
                      
  WEEKS     1 - 2          3 - 4          5 - 6          7 - 8
  PHASE   [ Phase 1 ]    [ Phase 2 ]    [ Phase 3 ]    [ Phase 4 ]
          Database &     Prioritized    Remote App     LLM Grounding &
          Audit Ledger   Dual SERP      & Rollback     Operational
          Hardening      Runner         UX             Deployment
```

---

### Phase 1: Database Hardening, SSOT & Audit Ledger Engine (Weeks 1–2)

**Objective**: Upgrade `peps.db` into a multi-user, audit-compliant database supporting remote transactions and rollback integrity.

#### Deliverables & Tasks:
1. **Schema Migration & Audit Table Implementation (`db.py`)**:
   * Create `verification_audit_log` with indexes on `person_id`, `account_id`, and `created_at`.
   * Add `last_modified_by` and `audit_version` columns to `social_accounts`.
2. **Transactional State Machine (`db.py`)**:
   * Implement `record_verification(account_id, new_status, verifier_id, notes)` wrapped in an atomic SQLite transaction.
   * Implement `revert_verification(log_id, verifier_id, reason)` which recalculates and restores the prior state while logging the reversal event.
   * Implement `get_audit_history(person_id)` returning the complete chronological timeline for any candidate.
3. **SSOT API Endpoints (`app.py`)**:
   * Refactor `POST /api/verify` to require `verifier_id` and optional `notes`.
   * Add `POST /api/revert` taking `{ log_id, verifier_id, reason }`.
   * Add `GET /api/candidates/<person_id>/audit` for timeline rendering.
4. **Secure Tunnel & SSOT Gateway Setup**:
   * Configure persistent tunnel configuration (via ngrok or Tailscale) allowing remote verifiers to hit `http://localhost:9090` without exposing the local network.

---

### Phase 2: 5-Tier Prioritization Queue & Dual-Engine SERP Runner (Weeks 3–4)

**Objective**: Implement the candidate prioritization hierarchy and dual-provider search routing to maximize hit rate per dollar.

#### Deliverables & Tasks:
1. **5-Tier Prioritization Classifier (`query_builder.py`)**:
   * **Tier 1 (Metros)**: Auto-tag candidates from 8 major metros (Johannesburg, Cape Town, eThekwini, Ekurhuleni, Tshwane, Nelson Mandela Bay, Buffalo City, Mangaung).
   * **Tier 2 (National Party PR Lists)**: Tag high-order PR candidates from major parties.
   * **Tier 3 (Contested Key Councils)**: Filter swing municipalities (e.g., Knysna, Oudtshoorn, Mogale City).
   * **Tier 4 (National Party Ward Candidates)**: Ward nominees with verified party backing.
   * **Tier 5 (Independents & Micro-Parties)**: Low-density, high-entropy candidates scheduled last.
2. **Dual-Provider SERP Orchestrator (`run_pipeline.py`)**:
   * **Primary Scheduled Engine (Serpent API)**:
     * Rate-limiter: Paced strictly at 200 requests/hour, 1,000 requests/day.
     * Dual-Query: Executes Google + Bing searches per candidate ($0.60 per 1k requests).
   * **Burst Failover Engine (SerpStack / Google Vertex)**:
     * Configured for Google-only high-throughput extraction during pre-election sprint weeks.
     * Dynamic thresholding: Automatically engages when ingestion queues require >1,000 queries/day.
3. **Rate-Limit & Cost Guardrails**:
   * Daily expenditure cap ($1.50/day hard limit on routine runs).
   * Dead-letter queue for HTTP 429 (Too Many Requests) with exponential backoff.

---

### Phase 3: Remote Verifier Web Interface & Reversibility UX (Weeks 5–6)

**Objective**: Deliver a responsive, high-speed verification dashboard accessible to remote analysts with zero setup.

#### Deliverables & Tasks:
1. **Verifier Authentication & Session Attribution (`static/index.html`)**:
   * Add persistent Verifier ID prompt modal (`👤 Verifier: [ Analyst Name ]`).
   * Store `verifier_id` in browser memory and include it in all verification API requests.
2. **Interactive Candidate Audit Drawer**:
   * In the candidate inspection drawer, render a chronological **Audit Trail Timeline**:
     * Timestamp (UTC)
     * Verifier Name & Avatar
     * State Change (e.g. `Unverified ➔ Confirmed (X/Twitter)`)
     * Justification Notes & Evidence Snippet
   * Add a `[ ↩ Revert Decision ]` button on verified accounts for immediate rollback.
3. **Ward & Councillor Type Filtering**:
   * Expose the 5 prioritization tiers directly in the search and filter toolbar.
   * Add rapid-triage shortcuts (keyboard hotkeys: `[V]` to verify, `[X]` to reject, `[N]` next candidate).
4. **Auto-Detection of Backend Mode**:
   * The web app automatically detects if the live SQLite API (`localhost:9090` or tunnel URL) is reachable:
     * If online: Reads/writes directly to SQLite SSOT.
     * If offline: Switches to read-only demonstration mode with export options.

---

### Phase 4: Grounded LLM Tuning, Export Automation & Operational Rollout (Weeks 7–8)

**Objective**: Refine prompt scoring accuracy, automate open-data outputs, and train the verification team.

#### Deliverables & Tasks:
1. **LLM Prompt Strengthening Loop (`evaluator.py`)**:
   * Ingest human verification decisions as a continuous test benchmark.
   * Mine false-positive and false-negative patterns (e.g., confusing provincial namesakes with local ward councillors).
   * Refine geographic triangulation bonuses (+0.30 for specific suburb/town matches).
2. **Open Data Export Pipelines (`build_static_site.py`)**:
   * Generate schema-valid **Popolo JSON** distributions containing full candidate profiles, social links, and verification metadata.
   * Automated bidirectional sync to **Google Sheets** for stakeholders and civil society partners.
   * Publish static snapshots to GitHub Pages as public transparency releases.
3. **Operational Documentation & Verifier Standard Operating Procedures (SOP)**:
   * Verification handbook detailing OSINT verification standards (photo matching, bio keywords, local issue corroboration).
   * Guidelines on dispute resolution and audit trail notes.

---

## 4. Operational Roles & Resource Allocation

| Role | Core Responsibilities | Commitment | Monthly Cost | 6-Month Total |
| :--- | :--- | :--- | :--- | :--- |
| **Lead Data & Pipeline Engineer** | System maintenance, SERP orchestrator, database migrations, LLM prompt engineering, SSOT tunnel stability. | 20 hrs / month ($60/hr) | $1,200 | **$7,200** |
| **OSINT Lead & Verification Specialist** | Daily pipeline ingestion, queue triage, reviewing borderline scores (0.45–0.70), supervisor review of audit logs. | 35 hrs / month ($30/hr) | $1,050 | **$6,300** |
| **Remote Verifiers (Pool of 2–3 Analysts)** | Distributed review of candidate accounts during sprint campaigns, applying verification criteria, attaching notes. | Integrated in OSINT allocation | Included above | Included above |
| **Dual SERP API Ingestion** | Serpent API (Google & Bing primary) + SerpStack/Vertex burst buffer. | ~30,000 queries / mo | ~$35 | **~$210** |
| **LLM Inference Tokens** | Grounded snippet validation (Gemini / Claude / GPT token passes). | ~100k snippets / mo | ~$25 | **~$150** |
| **Infrastructure & Hosting** | Local workstation, GitHub Pages, SSL tunnel. | Flat | $0 | **$0** |
| **TOTAL OPERATING BUDGET** | | | **~$2,310 / mo** | **~$13,860** |

---

## 5. Risk Assessment & Mitigation Strategy

| Risk Scenario | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **1. Split-Brain Data Drift**<br>(Remote verifiers disagreeing with local search workers) | High | All updates write to `verification_audit_log` via atomic SQLite transactions on the SSOT backend. If offline, the client locks into read-only mode until connection is re-established. |
| **2. Erroneous / Malicious Verification**<br>(Incorrect account confirmed as a PEP) | High | **Reversibility State Machine**: Any verification can be rolled back in 1 click. Full attribution records who made the change, when, and why. |
| **3. SERP Rate-Limit Throttling**<br>(Provider bans or IP blocks during high-volume runs) | Medium | Primary runner is throttled to 200 req/hr and 1,000 req/day. Urgent loads switch automatically to the Google-only burst provider (SerpStack / Vertex AI). |
| **4. Hallucinations & Identity Confusion**<br>(Candidates with common South African names) | High | Grounded prompt requires three-point triangulation: (1) Exact Name, (2) Municipal/Ward Geographic Anchor, and (3) Political Party Anchor. Scores below 0.60 require mandatory human review. |
| **5. Remote Verifier Fatigue / Backlog** | Low | High-confidence matches (>0.85) are prioritized for fast-track verification; Tier 5 candidates are only queried once Tiers 1–3 are fully cleared. |

---

## 6. Milestones & Acceptance Criteria

* [ ] **Milestone 1 (End of Week 2)**: Database schema updated with `verification_audit_log`; API supports `POST /api/verify` with verifier identity and `POST /api/revert` for rollbacks.
* [ ] **Milestone 2 (End of Week 4)**: 5-Tier input prioritization active in `query_builder.py`; dual-provider SERP runner executing rate-limited queries across Google and Bing.
* [ ] **Milestone 3 (End of Week 6)**: Remote verifier UI live with audit timeline, verifier handle badge, ward filters, and 1-click rollback button.
* [ ] **Milestone 4 (End of Week 8)**: 3,797+ candidate baseline processed; LLM prompt accuracy verified against human benchmark; live sync to Google Sheets and Popolo JSON export operational.
