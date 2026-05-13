# VIKAS — Sentiment Analyser Claude Prompts
**Version:** 1.0
**Target models:** Claude Haiku (Stage 3 high-volume), Claude Sonnet (Stage 3 low-confidence, Stage 4 trend analysis)
**Placeholder pattern:** `UPPERCASE_PLACEHOLDER` — replaced via Python `.replace()`, never f-string interpolation
**Output discipline:** every prompt returns strict JSON; defensive parser validates against Pydantic contract on the consuming side

---

## Prompt Registry Entries

Each prompt lives in `prompt_registry` table as: `(namespace, name, version, body, hash)`. Namespace for all: `sentiment_analyser`.

---

## 1. Polarity Classifier — English (Haiku Tier)

**Registry key:** `sentiment_analyser.polarity_classifier_en.v1`
**Model tier:** Fast (Claude Haiku 4.5)
**Use when:** language='en' AND VADER confidence < 0.85
**Average cost:** ~$0.0001 per mention

```
You are a sentiment classifier for political content about Indian government schemes. Classify the polarity of the text below. Be precise. Sarcasm and rhetorical questions are common in political content — read them carefully.

Output strict JSON only. No prose. No markdown fences. No explanation outside the JSON.

Schema:
{
  "polarity": "positive" | "negative" | "neutral" | "mixed",
  "polarity_score": <float between -1.0 and 1.0>,
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<one sentence, max 20 words, explaining the classification>",
  "contains_sarcasm": <true | false>,
  "is_about_scheme": <true | false>
}

Rules:
- "positive" = the speaker expresses approval, satisfaction, or praise toward the scheme or its execution
- "negative" = the speaker expresses criticism, dissatisfaction, complaint, or accusation
- "neutral" = factual reporting, announcement, or description without evaluative stance
- "mixed" = the text contains both clearly positive and clearly negative statements about the scheme
- If the text is not actually about a government scheme, set "is_about_scheme" to false and use "neutral" with confidence 1.0
- polarity_score: -1.0 = strongly negative, 0.0 = neutral, +1.0 = strongly positive
- confidence: lower it when text is short, ambiguous, or sarcastic

CONTEXT:
Scheme reference: SCHEME_NAME
District reference: DISTRICT_NAME
Source type: SOURCE_TYPE

TEXT TO CLASSIFY:
"""
MENTION_TEXT
"""

JSON output:
```

**Placeholders:**
- `SCHEME_NAME` — matched scheme key, e.g. "Madurai Smart City"
- `DISTRICT_NAME` — matched district or "unknown"
- `SOURCE_TYPE` — e.g. "news_article", "youtube_comment", "telegram_message"
- `MENTION_TEXT` — the cleaned content text, max 2000 characters

**Pydantic contract:**
```python
class PolarityOutput(BaseModel):
    polarity: Literal["positive", "negative", "neutral", "mixed"]
    polarity_score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(max_length=200)
    contains_sarcasm: bool
    is_about_scheme: bool
```

---

## 2. Polarity Classifier — Tamil and Mixed-Script (Sonnet Tier)

**Registry key:** `sentiment_analyser.polarity_classifier_ta.v1`
**Model tier:** Standard (Claude Sonnet 4.6)
**Use when:** language IN ('ta', 'mixed', 'unknown')
**Average cost:** ~$0.001 per mention

```
You are a sentiment classifier for Tamil and Tamil-English mixed (Tanglish) content about Indian government schemes. Classify the polarity of the text below.

Tamil political content frequently uses:
- Sarcasm and rhetorical questions
- Mixed script (Tamil and English in the same sentence)
- Regional idioms specific to Madurai, Coimbatore, and Tamil Nadu generally
- Honorific or hostile prefixes/suffixes for politicians

Read carefully for these patterns. Do not assume Tamil = positive or Tamil = negative.

Output strict JSON only. No prose. No markdown fences. No explanation outside the JSON.

Schema:
{
  "polarity": "positive" | "negative" | "neutral" | "mixed",
  "polarity_score": <float between -1.0 and 1.0>,
  "confidence": <float between 0.0 and 1.0>,
  "language_observed": "ta" | "en" | "mixed",
  "reasoning": "<one sentence, max 25 words>",
  "reasoning_tamil_quoted": "<if Tamil text drove the decision, quote up to 10 words of the key phrase; else empty string>",
  "contains_sarcasm": <true | false>,
  "is_about_scheme": <true | false>
}

Rules:
- "positive" = approval, satisfaction, praise toward the scheme
- "negative" = criticism, complaint, accusation, or expression of harm caused
- "neutral" = factual or descriptive without stance
- "mixed" = contains both positive and negative statements about the same scheme
- For Tanglish, treat Tamil and English content together — do not classify only one language
- For sarcasm, classify the intended polarity (sarcastic praise = negative)
- polarity_score: -1.0 strongly negative to +1.0 strongly positive
- Lower confidence when text is short, ambiguous, or relies on context not present

CONTEXT:
Scheme reference: SCHEME_NAME
District reference: DISTRICT_NAME
Source type: SOURCE_TYPE
Detected language: DETECTED_LANGUAGE

TEXT TO CLASSIFY:
"""
MENTION_TEXT
"""

JSON output:
```

**Placeholders:**
- `SCHEME_NAME`, `DISTRICT_NAME`, `SOURCE_TYPE` — same as above
- `DETECTED_LANGUAGE` — from fasttext: 'ta', 'mixed', 'unknown'
- `MENTION_TEXT` — content, max 2000 characters

---

## 3. Batch Polarity Classifier (Cost Optimization)

**Registry key:** `sentiment_analyser.polarity_batch.v1`
**Model tier:** Fast (Claude Haiku 4.5)
**Use when:** ≥5 short mentions (<500 chars each) need classification; cuts cost ~70% vs per-item
**Average cost:** ~$0.0003 per 10-mention batch

```
You are a sentiment classifier for political content about Indian government schemes. Classify each text in the batch below.

Output a strict JSON array with one object per input text, in the same order. No prose. No markdown fences.

Schema for each array element:
{
  "id": "<the id from the input>",
  "polarity": "positive" | "negative" | "neutral" | "mixed",
  "polarity_score": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "is_about_scheme": <true | false>
}

Rules:
- positive = approval, praise, satisfaction with the scheme
- negative = criticism, complaint, accusation
- neutral = factual or descriptive without stance
- mixed = contains both positive and negative statements
- If text is not about the referenced scheme, mark is_about_scheme false and use neutral
- Apply sarcasm detection: sarcastic praise → negative
- Return one object per input, preserving order

CONTEXT:
Scheme reference: SCHEME_NAME
District reference: DISTRICT_NAME

INPUTS (JSON array):
MENTION_BATCH_JSON

JSON output:
```

**Placeholders:**
- `SCHEME_NAME`, `DISTRICT_NAME` — applied to all items in batch
- `MENTION_BATCH_JSON` — array like `[{"id":"u1","text":"..."},{"id":"u2","text":"..."}]`, max 20 items per batch

**Pydantic contract:**
```python
class BatchPolarityItem(BaseModel):
    id: str
    polarity: Literal["positive", "negative", "neutral", "mixed"]
    polarity_score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    is_about_scheme: bool

class BatchPolarityOutput(BaseModel):
    items: list[BatchPolarityItem]
```

---

## 4. Theme Extraction (Novel Themes Discovery)

**Registry key:** `sentiment_analyser.theme_discovery.v1`
**Model tier:** Standard (Claude Sonnet 4.6)
**Use when:** quarterly batch of high-volume mentions that didn't match existing theme taxonomy
**Purpose:** surface emerging themes for human curation into taxonomy

```
You are analyzing political mentions about Indian government schemes to discover recurring themes. The taxonomy below is the current known set. Your job is to find themes that are present in the sample but NOT in the taxonomy.

Output strict JSON only. No prose. No markdown fences.

Schema:
{
  "novel_themes": [
    {
      "theme_label_en": "<short label, 2-4 words, English>",
      "theme_label_ta": "<short label in Tamil if Tamil-relevant, else empty string>",
      "description": "<one sentence describing the theme, max 25 words>",
      "frequency_estimate": <integer count of mentions in the sample touching this theme>,
      "example_mention_ids": [<up to 3 mention ids that exemplify the theme>],
      "polarity_skew": "mostly_positive" | "mostly_negative" | "mixed" | "neutral",
      "recommend_add_to_taxonomy": <true | false>,
      "rationale_for_recommendation": "<one sentence>"
    }
  ],
  "coverage_assessment": "<one sentence describing how well the existing taxonomy covers the sample>"
}

Rules:
- Only surface themes that appear in ≥3 mentions in the sample
- Themes must be specific enough to be actionable, not so specific they apply to one mention
- A theme is "novel" if no existing taxonomy entry covers it semantically
- recommend_add_to_taxonomy = true only if frequency is meaningful AND theme is distinct
- Examples: "delayed pension disbursement" is good; "people are unhappy" is too vague

EXISTING THEME TAXONOMY:
EXISTING_THEMES_JSON

SAMPLE MENTIONS (JSON array, each with id, text, polarity):
SAMPLE_MENTIONS_JSON

JSON output:
```

**Placeholders:**
- `EXISTING_THEMES_JSON` — array like `[{"theme_key":"water_supply","description":"...","patterns_en":[...]}]`
- `SAMPLE_MENTIONS_JSON` — up to 100 mentions, format `[{"id":"...","text":"...","polarity":"..."}]`

---

## 5. Theme Classification (Per Mention)

**Registry key:** `sentiment_analyser.theme_classifier.v1`
**Model tier:** Fast (Claude Haiku 4.5)
**Use when:** pattern-based theme extraction returned <2 themes AND mention is high-weight (verified source or high engagement)
**Purpose:** fallback theme tagging for nuanced content where keyword matching misses

```
You are classifying a political mention against a fixed theme taxonomy. Identify ONLY themes from the provided taxonomy that the mention clearly expresses. Do not invent new themes.

Output strict JSON only. No prose. No markdown fences.

Schema:
{
  "matched_themes": [
    {
      "theme_key": "<exact theme_key from taxonomy>",
      "confidence": <float 0.0 to 1.0>,
      "evidence_quote": "<up to 15 words from the mention text that support this theme>"
    }
  ],
  "no_match_reason": "<if matched_themes is empty, one sentence explaining why; else empty string>"
}

Rules:
- Only use theme_key values from the taxonomy below — never invent
- Include a theme only if confidence ≥ 0.6
- Maximum 5 themes per mention
- evidence_quote must be a substring (or close paraphrase under 15 words) of the original mention
- If nothing clearly matches, return empty array and explain in no_match_reason

THEME TAXONOMY:
THEME_TAXONOMY_JSON

MENTION TEXT:
"""
MENTION_TEXT
"""

Context: scheme=SCHEME_NAME, district=DISTRICT_NAME, language=DETECTED_LANGUAGE

JSON output:
```

**Placeholders:**
- `THEME_TAXONOMY_JSON` — `[{"theme_key":"water_supply","description":"...","examples":["..."]}]`
- `MENTION_TEXT` — max 2000 chars
- `SCHEME_NAME`, `DISTRICT_NAME`, `DETECTED_LANGUAGE`

---

## 6. Entity & Claim Extraction

**Registry key:** `sentiment_analyser.entity_extractor.v1`
**Model tier:** Fast (Claude Haiku 4.5)
**Use when:** mention has source_weight ≥ 0.7 (journalist content, high-reach posts)
**Purpose:** extract structured entities and verifiable claims for downstream fact-checking

```
You are extracting entities and factual claims from a political mention about an Indian government scheme. Be precise. Do not infer beyond what is stated.

Output strict JSON only. No prose. No markdown fences.

Schema:
{
  "schemes_mentioned": [<list of scheme names exactly as they appear in text>],
  "districts_mentioned": [<list of place names exactly as they appear>],
  "persons_mentioned": [
    {
      "name": "<as appearing>",
      "role_if_stated": "<e.g. 'MLA', 'Mayor', 'beneficiary' or empty string>",
      "polarity_toward": "positive" | "negative" | "neutral" | "not_evaluative"
    }
  ],
  "factual_claims": [
    {
      "claim": "<the claim as stated, max 30 words>",
      "is_verifiable": <true | false>,
      "claim_type": "statistic" | "event" | "promise" | "accusation" | "comparison",
      "involves_numbers": <true | false>
    }
  ],
  "quoted_statements": [
    {
      "speaker": "<who said it, if named>",
      "quote": "<the quoted text, max 50 words>"
    }
  ]
}

Rules:
- Extract only what is explicitly in the text — do not infer or expand
- For Tamil text, transliterate person names to Latin script if not already
- factual_claims: verifiable means could in principle be checked against records
- Empty arrays are valid — return [] rather than omitting fields
- Do not extract claims from clearly opinionated statements like "the scheme is bad"

MENTION TEXT:
"""
MENTION_TEXT
"""

Source type: SOURCE_TYPE
Language: DETECTED_LANGUAGE

JSON output:
```

**Placeholders:** standard set.

---

## 7. Spike Detection & Alert Reasoning

**Registry key:** `sentiment_analyser.spike_analyzer.v1`
**Model tier:** Standard (Claude Sonnet 4.6)
**Use when:** Stage 4 trend detector flags a sudden negative spike (e.g., negative mention count rises >2x rolling 7-day average)
**Purpose:** generate human-readable explanation of what's happening for the morning ops dashboard

```
You are a political communication analyst. The system has detected a sudden shift in sentiment for a government scheme. Analyze the recent mentions and produce a concise situation summary.

Output strict JSON only. No prose. No markdown fences.

Schema:
{
  "situation_summary": "<2-3 sentences describing what changed and why, max 80 words>",
  "primary_drivers": [
    {
      "driver_description": "<one sentence>",
      "evidence_mention_ids": [<up to 3 mention ids that exemplify this driver>],
      "estimated_share_pct": <integer 0-100, approximate share of the spike attributable to this driver>
    }
  ],
  "is_organic_or_amplified": "organic" | "amplified" | "uncertain",
  "amplification_signals": [<list of signals supporting amplification verdict, e.g. 'identical phrasing across accounts', 'sudden volume from new accounts'>],
  "recommended_response_type": "address_concern" | "factual_correction" | "amplify_positive_counter" | "monitor_only" | "escalate_to_compliance",
  "urgency": "low" | "medium" | "high" | "critical",
  "rationale_for_urgency": "<one sentence>"
}

Rules:
- Base every claim on the provided mention evidence — do not speculate
- "amplified" = signs of coordinated activity (similar wording, account clustering, bot-like timing)
- "organic" = diverse phrasing, varied accounts, natural distribution
- recommended_response_type guides the next agent, not the human; be conservative
- urgency=critical only when negative volume sustained or involves serious allegations
- Avoid recommending content production for "monitor_only"; that's the point of it

CONTEXT:
Scheme: SCHEME_NAME
District: DISTRICT_NAME
Window analyzed: WINDOW_START to WINDOW_END
Baseline (rolling 7-day avg): BASELINE_STATS
Current window stats: CURRENT_STATS

TOP MENTIONS DRIVING THE SPIKE (JSON array):
SPIKE_MENTIONS_JSON

JSON output:
```

**Placeholders:**
- `BASELINE_STATS` — JSON like `{"avg_mentions_per_day": 12, "avg_negative_pct": 22, "avg_weighted_polarity": -0.1}`
- `CURRENT_STATS` — same shape for the current window
- `SPIKE_MENTIONS_JSON` — up to 25 mentions, with id, text, source, polarity, source_weight, published_at
- `WINDOW_START`, `WINDOW_END` — ISO timestamps

---

## 8. Source Credibility Scoring (One-Time Per New Source)

**Registry key:** `sentiment_analyser.source_credibility.v1`
**Model tier:** Standard (Claude Sonnet 4.6)
**Use when:** a new source appears in raw_mentions that doesn't have a credibility score yet
**Purpose:** assign initial source weight for use in Stage 4 aggregation

```
You are evaluating the credibility and reach of a content source for use in political sentiment aggregation. Output a credibility weight and rationale.

Output strict JSON only. No prose. No markdown fences.

Schema:
{
  "source_type": "mainstream_news" | "regional_news" | "citizen_journalist" | "social_media_individual" | "social_media_amplifier" | "official_government" | "political_party" | "ngo_advocacy" | "blog" | "unknown",
  "estimated_reach": "national" | "state" | "district" | "local" | "niche" | "unknown",
  "editorial_standards": "high" | "medium" | "low" | "none" | "unknown",
  "known_political_lean": "left" | "right" | "ruling_party_aligned" | "opposition_aligned" | "independent" | "unknown",
  "credibility_weight": <float 0.0 to 1.5>,
  "reach_weight": <float 0.0 to 1.5>,
  "rationale": "<2 sentences explaining the assigned weights, max 50 words>",
  "requires_human_review": <true | false>,
  "human_review_reason": "<one sentence if requires_human_review true; else empty string>"
}

Rules:
- credibility_weight 1.0 is the baseline; 1.5 is high editorial credibility; 0.3 is low/unverified
- reach_weight 1.0 is the baseline; raise for high-circulation national outlets, lower for niche
- If you cannot determine the source from the data provided, mark fields "unknown" and require human review
- Do NOT inflate weights without evidence — default to caution

SOURCE INFORMATION:
Source identifier: SOURCE_IDENTIFIER
Domain or handle: SOURCE_HANDLE
Sample content from this source (3-5 mentions):
SOURCE_SAMPLES_JSON

Any public information visible in the samples: bio text, follower counts, verified badges, etc.

JSON output:
```

**Placeholders:**
- `SOURCE_IDENTIFIER` — e.g. "youtube_channel:UCxxxxx"
- `SOURCE_HANDLE` — e.g. "@CovaiPostNews"
- `SOURCE_SAMPLES_JSON` — sample mentions from this source

---

## 9. Defensive JSON Parser (Consumer-Side)

Every LLM output must be parsed defensively. Standard pattern applied to all of the above:

```python
import json
import re
from pydantic import ValidationError

def parse_llm_json(raw: str, contract: type[BaseModel]) -> BaseModel:
    """
    Defensive JSON parser. Strips fences, finds JSON, validates against Pydantic contract.
    Raises ValueError on unrecoverable failure; never silently returns malformed data.
    """
    # 1. Strip markdown fences if present
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    cleaned = re.sub(r'\s*```$', '', cleaned)
    
    # 2. Try direct parse
    try:
        data = json.loads(cleaned)
        return contract.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        pass
    
    # 3. Extract first balanced JSON object/array
    extracted = _extract_balanced_json(cleaned)
    if extracted:
        try:
            data = json.loads(extracted)
            return contract.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            pass
    
    # 4. Last resort: regex for the schema's first field
    # (omitted here for brevity; per-contract recovery if needed)
    
    raise ValueError(f"Could not parse LLM output against {contract.__name__}")

def _extract_balanced_json(text: str) -> str | None:
    # Find first '{' or '[' and walk to matching closer respecting nesting + strings
    # Standard implementation; omitted here
    ...
```

---

## 10. Prompt Hygiene Rules (Apply to All)

These are the rules the team enforces on every prompt entering the registry. The prompts above already follow them:

1. **Strict JSON output, no prose.** Every prompt ends with "JSON output:" to anchor the model.
2. **Schema declared in the prompt.** Don't rely on the model inferring the schema — show it.
3. **Rules block.** Edge cases handled explicitly: sarcasm, mixed language, empty arrays, what to do when unsure.
4. **UPPERCASE_PLACEHOLDER tokens only.** No f-string interpolation; replacement via `.replace()` in code.
5. **No prompt instructs the model to "be helpful" or "be smart".** Specific instructions only.
6. **Cost-tier annotation in registry.** Each prompt locked to a model tier; changing tier requires a registry update.
7. **Versioned and hash-locked.** Prompt body hashed at registry insert; agent runs log prompt_hash for reproducibility.
8. **Tested with golden traces.** Each prompt has 5–10 fixed inputs with expected outputs in the regression suite. CI runs them on every PR touching the prompt.
9. **One-job prompts.** Each prompt does one thing. No "classify and summarize and tag" multi-task prompts — break them up.
10. **No PII leakage in prompts.** Don't embed beneficiary names, phone numbers, or identifiable individuals unless legally cleared.

---

## 11. Usage Order in the Pipeline

```
Stage 2 (Filtering):
  - Pattern-based filters first (cheap, deterministic)
  - No LLM here

Stage 3 (Analysis), per mention:
  1. Language detection (fasttext, not LLM)
  2. Pattern-based theme tagging (no LLM)
  3. Polarity classification:
     - English + high VADER confidence → no LLM
     - English + low VADER confidence → Prompt 1 (Haiku)
     - Tamil/mixed → Prompt 2 (Sonnet)
     - Batched short mentions → Prompt 3 (Haiku)
  4. Theme classification fallback (high-weight only, missing themes):
     → Prompt 5 (Haiku)
  5. Entity extraction (high-weight only):
     → Prompt 6 (Haiku)

Stage 4 (Aggregation), periodic:
  - Aggregation itself: no LLM (pure SQL + pandas)
  - Spike alerts → Prompt 7 (Sonnet)
  - New source onboarding → Prompt 8 (Sonnet, one-time)
  - Quarterly theme discovery → Prompt 4 (Sonnet)
```

---

## 12. Cost Estimate (Per 1,000 Mentions Processed)

| Component | Mentions hitting LLM | Model | Cost |
|---|---|---|---|
| English low-confidence polarity | ~150 (~15% of English volume) | Haiku | ~$0.015 |
| Tamil/mixed polarity | ~300 (~30% of total volume) | Sonnet | ~$0.30 |
| Batched short mentions | ~200 | Haiku batch | ~$0.006 |
| Theme classification fallback | ~50 (high-weight only) | Haiku | ~$0.005 |
| Entity extraction | ~50 (high-weight only) | Haiku | ~$0.010 |
| **Per 1,000 mentions** | | | **~$0.35** |
| Spike alerts | ~3/day | Sonnet | ~$0.05/day |
| Source onboarding | ~1/week | Sonnet | negligible |
| Quarterly theme discovery | 1 batch | Sonnet | ~$0.50 |

**Per-org monthly estimate** at 100K mentions: ~$35–50 in LLM cost for sentiment analysis. Well within budget tier.

---

## 13. What Not to Use LLM For (Cost Discipline)

These are tempting but wrong:
- **Language detection** — use `langdetect` with `DetectorFactory.seed = 0` for
  determinism. Never use LLM for language detection.
- **Deduplication** — MinHash/SimHash is purpose-built; LLM is wasteful
- **Spam detection** — simple heuristics outperform LLM for known patterns
- **Aggregation math** — SQL and pandas; LLM cannot count reliably
- **Per-source mention counts** — pure SQL
- **Trend computation** — pandas rolling windows

LLM only earns its place where deterministic methods fail: nuanced polarity, novel theme discovery, situation reasoning. Everything else is rules and SQL.

— End of prompt registry entries —