# Phase 4: AI-Agent Outreach System - Overview

## Vision

Build a zero-cost, fully automated AI-agent outreach system that contacts 100-200 qualified wholesaler leads per month across multiple Florida markets, achieving 1.5-3% deal close rates through intelligent multi-touch campaigns.

## Core Capabilities

- **Automated Contact Enrichment**: Extract owner phone/email from public records via custom web scrapers
- **AI-Powered Messaging**: Generate personalized, compliant outreach messages using local LLM
- **Multi-Channel Communication**: Email + SMS drip campaigns (3-5 touches over 14-21 days)
- **Intelligent Conversations**: Sentiment analysis and intent detection to identify interested sellers
- **Human Handoff**: Auto-escalate qualified leads when interest detected
- **Multi-Market Scale**: Expand from Orange County to 5+ Florida counties
- **ROI Tracking**: Complete analytics dashboard for campaign performance

---

## System Architecture

```
Lead Scoring (Phases 1-3)
         ↓
    CRM Foundation
         ↓
  Contact Enrichment (Skip Tracing)
         ↓
   Local LLM Infrastructure
         ↓
Multi-Channel Outreach Engine
         ↓
 AI Agent Conversation Handler
         ↓
    [Human Handoff → Deal!]
```

---

## Technology Stack (Zero-Cost Focus)

| Component | Technology | Cost |
|-----------|-----------|------|
| **LLM** | Ollama + Llama 3.1 8B | $0 (self-hosted) |
| **Sentiment Analysis** | HuggingFace transformers | $0 (local) |
| **Web Scraping** | BeautifulSoup4 + Playwright | $0 |
| **Task Queue** | Celery + Redis | $0 (existing) |
| **SMS** | Twilio | ~$0.0075/SMS (free trial $15) |
| **Email** | Gmail SMTP | $0 (free tier) |
| **Database** | PostgreSQL | $0 (existing) |
| **Compliance** | FTC DNC API | $0 |

**Total Monthly Cost**: ~$15-30 (SMS only)

---

## Phase Breakdown

### Phase 4A: Documentation Cleanup & Reorganization

**Objective**: Create clean repository structure with organized documentation.

**What Will Be Done**:
- Create `docs/` directory with subdirectories: setup/, guides/, architecture/, summaries/
- Move all `.md` files from root into appropriate docs subdirectories
- Keep only `README.md` and `QUICKSTART.md` in repository root
- Update all internal documentation links and cross-references
- Update QUICKSTART.md with new documentation paths

**Target Directory Structure**:
```
wholesaler/
├── README.md
├── QUICKSTART.md
├── PHASE_4_OVERVIEW.md
└── docs/
    ├── setup/          (alerts_setup.md, ml_training_guide.md)
    ├── guides/         (testing_guide.md, database_schema.md)
    ├── architecture/   (phase3_api_dashboard.md, phase3c_ml_auth.md)
    └── summaries/      (phase2A/2B/2C_summary.md)
```

---

### Phase 4B: CRM Foundation & Database Schema

**Objective**: Build customer relationship management (CRM) database infrastructure.

**What Will Be Done**:

**New Database Tables** (6 tables):
1. **contacts** - Owner contact information (phone, email, opt-out status, verification)
2. **outreach_campaigns** - Campaign configurations (name, type, target tier/markets, schedule)
3. **communications** - Message log (sent/received, channel, sentiment, intent)
4. **lead_statuses** - Workflow states (contacted → interested → negotiating → deal closed)
5. **message_templates** - AI prompt templates with personalization variables
6. **conversation_states** - FSM state tracking for AI agent conversations

**Key Fields**:
- Contact: parcel_id, phone (E.164 format), email, owner_name, opt_out (boolean)
- Campaign: name, target_tier, schedule_config (JSON), active (boolean)
- Communication: contact_id, campaign_id, direction (inbound/outbound), channel (sms/email), sentiment_score (-1 to 1), intent (interested/not_interested/question)
- LeadStatus: status (new/contacted/replied/interested/negotiating/deal_closed/opt_out), last_contact_date, assigned_to
- ConversationState: current_state, conversation_history (JSON), human_takeover (boolean)

**Additional Work**:
- Create Alembic migration for schema changes
- Build repository pattern for CRM entities (Contact, Campaign, Communication CRUD)
- Create FastAPI endpoints for CRM operations (create contact, create campaign, list communications, opt-out contact)
- Add Pydantic schemas for request/response validation

---

### Phase 4C: Skip Tracing & Contact Enrichment

**Objective**: Extract owner contact information (phone/email) from public records.

**What Will Be Done**:

**Web Scrapers**:
- Orange County Property Appraiser scraper (owner mailing address extraction)
- Additional Florida public records sources
- CAPTCHA handling, IP rotation strategies, rate limiting
- Batch processing with retry logic

**Contact Validation**:
- Phone number validation and E.164 formatting (+1XXXXXXXXXX)
- Email validation (regex + DNS MX record check)
- Confidence scoring for scraped data
- Deduplication logic

**Manual Upload Interface**:
- API endpoint for bulk CSV upload (columns: parcel_id, phone, email, source)
- Batch validation and import processing
- Error reporting and skipped records log

**Data Management**:
- Link contacts to existing property records via parcel_id
- Track contact source (scraper vs manual_upload)
- Mark phone_verified and email_verified status
- Support for multiple contacts per property

---

### Phase 4D: Local LLM Infrastructure

**Objective**: Set up self-hosted Llama 3.1 8B for message generation and response parsing.

**What Will Be Done**:

**Ollama Docker Service**:
- Add Ollama container to docker-compose.yml
- Pull and configure Llama 3.1 8B model (~4.7GB download)
- Expose API on port 11434
- Optional GPU support configuration for faster inference

**Prompt Engineering**:
- Initial contact template (consultative + problem-solving tone)
- Follow-up templates (touches 2-5, progressive urgency)
- Response templates (interested, question, objection handling)
- Variable injection system (owner_name, situs_address, distress_reason, market_context)
- Compliance footer with opt-out instructions

**LLM Integration**:
- Client wrapper for Ollama API
- Message generation with temperature control (0.7 for creativity)
- Message length constraints (SMS: 160 chars, email: 200-300 words)
- Response parsing and cleanup (remove quotes, extra whitespace, hallucinations)

**Intent Detection**:
- LLM-based intent classification (interested, not_interested, question, opt_out, unknown)
- Keyword fallback matching for reliability
- Confidence scoring

---

### Phase 4E: Multi-Channel Outreach Engine

**Objective**: Build automated outreach system with SMS/email sending, drip campaigns, and TCPA compliance.

**What Will Be Done**:

**Communication Channels**:
- SMS sender via Twilio API
- Email sender using existing SMTP infrastructure
- Message formatting for each channel (SMS: short, email: longer with formatting)
- Delivery tracking and error handling

**Drip Campaign System**:
- Finite state machine (FSM) for campaign progression
- Campaign states: not_started → touch_1_sent → touch_2_sent → ... → completed
- Configurable schedule (3-5 touches over 14-21 days)
- Dynamic next-touch scheduling based on campaign config

**Celery Task Queue**:
- Async task for sending individual messages
- Task scheduling for future touches
- Task cancellation when lead responds or opts out
- Retry logic for failed sends

**TCPA Compliance Safeguards**:
- National Do Not Call (DNC) Registry check via FTC API
- Quiet hours enforcement (no messages 9 PM - 8 AM)
- Rate limiting (max 1 message per day per contact)
- One-touch opt-out via "STOP" keyword detection
- Automatic campaign cancellation on opt-out
- Permanent opt-out logging with timestamp

**Additional Features**:
- Contact enrollment in campaigns
- Batch lead enrollment API
- Campaign pause/resume functionality
- Message preview before send

---

### Phase 4F: AI Agent Conversation Engine

**Objective**: Build intelligent response handling with sentiment analysis and human escalation.

**What Will Be Done**:

**Inbound Message Processing**:
- Twilio webhook for SMS responses
- Email webhook/polling for email replies
- Contact lookup by phone/email
- Automatic opt-out detection and processing

**Sentiment Analysis**:
- Local DistilBERT model for sentiment scoring
- Score range: -1.0 (very negative) to 1.0 (very positive)
- Batch processing for performance
- Sentiment logging in communications table

**Intent Detection**:
- LLM-based response classification
- Intent categories: interested, not_interested, question, opt_out, unknown
- Keyword fallback for reliability
- Intent logging for analytics

**Conversation State Management**:
- Update conversation_states table with each interaction
- Append messages to conversation_history (JSON array)
- Track current_state in FSM
- Identify conversation patterns (e.g., multiple questions = engaged)

**Decision Engine**:
- If intent = "interested" OR sentiment > 0.5 → Escalate to human
- If intent = "question" → Generate auto-reply via LLM
- If intent = "not_interested" → Mark lead as cold, stop campaign
- If intent = "opt_out" → Process opt-out immediately

**Human Handoff**:
- Mark conversation_states.human_takeover = TRUE
- Update lead_statuses to "interested"
- Cancel remaining campaign touches
- Send notification to user via SMS and email
- Include conversation history in notification
- Provide dashboard link for full context

**Auto-Reply Generation**:
- LLM generates contextual response to questions
- Includes conversation history for context
- Maintains consultative tone
- Keeps responses brief (2-3 sentences)
- Logs outbound auto-reply in communications

---

### Phase 4G: Multi-Market Expansion Framework

**Objective**: Scale from 13 Tier A leads/month (Orange County) to 100-200 leads/month via geographic expansion.

**What Will Be Done**:

**Market Addition**:
- Add 4 new Florida counties: Seminole, Osceola, Lake, Volusia
- Research and configure data sources for each county:
  - Parcel/property records (ArcGIS REST APIs)
  - Tax sale listings
  - Foreclosure filings
  - Code violations
  - Property appraiser sites

**Scraper Configuration System**:
- Market configuration registry (name, API URLs, appraiser site)
- Dynamic scraper initialization based on market code
- County-specific parsing logic
- Unified data model across all markets

**Lead Volume Strategy**:
- Include all Tier A leads (score ≥ 43) from all 5 counties
- Add high-scoring Tier B leads (score ≥ 38) to reach volume target
- Denote as "Tier B+" to distinguish from lower B leads
- Estimated: ~20 Tier A per county + ~20 Tier B+ per county = 200 leads/month

**Market-Specific Personalization**:
- County-specific message templates
- Local market context injection (e.g., "Orlando market is very active")
- Geographic references in messages
- Market tagging for analytics

**Data Source Auto-Discovery** (Helper):
- Tool to identify ArcGIS servers for a given county
- API endpoint testing and validation
- Schema inspection for available fields
- Configuration file generation

---

### Phase 4H: Analytics Dashboard & ROI Tracking

**Objective**: Provide visibility into campaign performance, response rates, and deal attribution.

**What Will Be Done**:

**Dashboard Pages** (Streamlit):
1. **Outreach Analytics Overview**
   - KPI cards: Messages Sent, Response Rate, Interest Rate, Deals Closed
   - Date range filtering
   - Channel comparison (SMS vs Email performance)
   - Campaign funnel visualization (Contacted → Responded → Interested → Deal)

2. **Campaign Performance**
   - List all campaigns with metrics
   - Campaign-specific response rates
   - Active vs completed campaigns
   - Touch-level analytics (which touch gets best responses)

3. **Conversation History Viewer**
   - Chat-style interface showing message threads
   - Sentiment score display
   - Intent classification labels
   - Human takeover indicators
   - Full conversation export

4. **ROI Dashboard**
   - Cost calculations (SMS fees, compute costs)
   - Revenue tracking (deals closed, average profit)
   - Cost per lead metrics
   - ROI percentage calculation
   - Break-even analysis

**Metrics Calculations**:
- Response rate: inbound messages / outbound messages
- Interest rate: interested responses / total responses
- Conversion rate: deals closed / leads contacted
- Channel effectiveness: response rate by SMS vs email
- Time-to-response: hours between contact and first reply
- Campaign completion rate: finished campaigns / started campaigns

**Data Aggregations**:
- Metrics by date range
- Metrics by campaign
- Metrics by market (county)
- Metrics by tier (A vs B+)
- Metrics by message template

**Deal Attribution**:
- Link closed deals back to originating campaign
- Track full lead journey (contacted → responded → interested → deal)
- Calculate time from first contact to close
- Identify highest-performing campaigns

---

## Success Criteria

### Technical Milestones
- 6 new CRM tables operational in production
- Llama 3.1 8B responding in <3 seconds
- Skip tracing achieving >70% contact data coverage
- Drip campaigns executing on schedule without errors
- Sentiment analysis showing consistent scoring
- Zero TCPA violations (100% DNC compliance, all opt-outs honored)

### Business KPIs
- 100-200 qualified leads enrolled in outreach monthly
- >3% response rate from contacted leads
- >30% of responses showing positive sentiment
- >10% of responses expressing interest in selling
- Cost per contacted lead <$0.50
- At least 1 deal closed per month attributable to outreach

### Quality Benchmarks
- LLM-generated messages sound natural and on-brand
- No spam complaints or carrier blocks
- Human handoff triggers fire correctly (no missed hot leads)
- Dashboard loads in <3 seconds with full data

---

## Risk Mitigation

| Risk | Mitigation Strategy |
|------|---------------------|
| **Web scraping legal concerns** | Only scrape public records, respect robots.txt, reasonable delays, don't overwhelm servers |
| **LLM hallucinations in messages** | Prompt engineering, temperature tuning, manual review of first 50 messages, regex cleanup |
| **TCPA violations** | Automatic DNC checks, one-touch opt-out, quiet hours, rate limiting, comprehensive audit logs |
| **Low response rates** | A/B test message templates, multi-touch sequences, deep personalization, test different send times |
| **Twilio account suspension** | Comply with terms of service, handle opt-outs immediately, don't spam, monitor sending reputation |
| **Compute constraints** | Llama 3.1 8B optimized for CPU, 2-3s response acceptable, batch processing where possible |
| **Skip trace data quality** | Manual upload option, multi-source scraping, validation before use, confidence scoring |

---

## Implementation Dependencies

```
Phase 4A (Docs)        → No dependencies
Phase 4B (CRM)         → No dependencies
Phase 4C (Skip Trace)  → Requires 4B (Contact table)
Phase 4D (LLM)         → No dependencies
Phase 4E (Outreach)    → Requires 4B, 4C, 4D
Phase 4F (AI Agent)    → Requires 4E
Phase 4G (Multi-Market)→ Requires 4E
Phase 4H (Analytics)   → Requires all previous phases
```

**Can run in parallel**:
- 4A + 4B + 4D (all independent)
- 4F + 4G (both depend on 4E)

---

## Configuration Requirements

### Environment Variables (.env additions)
- Twilio credentials (account SID, auth token, phone number)
- Ollama host URL and model name
- LLM parameters (temperature, max tokens)
- TCPA settings (quiet hours, max messages per day, DNC check enabled)
- User notification settings (phone, email for escalations)
- Multi-market configuration (list of active markets, tier thresholds)

### Makefile Commands (to be added)
- `make llm-setup` - Download Llama model
- `make skip-trace` - Run skip tracing for leads without contacts
- `make crm-shell` - Open Python shell with CRM models loaded
- `make test-sentiment` - Test sentiment analysis
- `make scrape-all-markets` - Scrape all 5 counties

### Docker Services (to be added)
- Ollama container for LLM inference

---

## Next Steps

1. **Approve this Phase 4 plan** - Confirm architecture and approach
2. **Phase 4A: Clean up documentation** - Reorganize docs directory
3. **Phase 4B: Design CRM schema** - Finalize table structures
4. **Set up Twilio** - Create account and get free trial credit
5. **Research county data sources** - Identify APIs for new markets

---

**Document Version**: 1.0
**Last Updated**: 2025-11-08
