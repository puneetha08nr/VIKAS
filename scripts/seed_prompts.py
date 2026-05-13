#!/usr/bin/env python
"""Seed the prompts table with starter prompts for all core agents.

Prompts are global (no org_id). Brand voice adjustments are injected at
runtime by the preference system, not stored as separate prompt rows.

Usage:
    python scripts/seed_prompts.py
    uv run python scripts/seed_prompts.py
"""
import asyncio
import sys
from pathlib import Path

# Put apps/api on the path so imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from db.session import org_session  # noqa: E402 — path must be set first
from core.prompt_registry import PromptRegistry  # noqa: E402

# ── Starter prompts ───────────────────────────────────────────────────────────
# These are intentionally minimal starters. Refine them via PromptRegistry.set()
# as you learn what works. Never hardcode prompts inside agents.

PROMPTS: dict[str, str] = {
    "keyword_research": """\
You are a keyword research specialist. Generate 10 related keywords for: SEED_KEYWORD

Return ONLY a JSON array, no markdown, no explanation:
[{"keyword": "", "volume": 0, "kd": 0.0, "cpc": 0.0, "intent": "", "reason": ""}]

intent must be one of: informational, commercial, transactional, navigational
cpc is estimated cost per click in USD
volume is estimated monthly searches
kd is keyword difficulty 0-10

Example:
[{"keyword": "project management app", "volume": 2000, "kd": 4.5, "cpc": 2.30, "intent": "commercial", "reason": "High buying intent"}]

Now generate 10 keywords for: SEED_KEYWORD\
""",

    "keyword_validator": """\
Evaluate these keywords for SEO content creation.

Return ONLY a JSON array. No code. No explanation. No markdown. No prose.
The first character of your response must be [
The last character of your response must be ]

Each object in the array must have exactly these four fields:
{"keyword_id": "the exact id from input", "keyword": "the keyword text", "worth_targeting": true, "reason": "one sentence"}

worth_targeting rules:
- true if: volume > 100 AND kd < 8 AND intent is commercial or transactional
- false if: volume < 50 OR kd > 9 OR intent is navigational
- true for all others (give benefit of the doubt)

Example output (copy this structure exactly):
[{"keyword_id": "abc-123", "keyword": "crm software", "worth_targeting": true, "reason": "Strong commercial intent with manageable difficulty."}]

Keywords to evaluate:
KEYWORD_BATCH_JSON\
""",

    "article_planner": """\
You are creating a detailed article outline optimized for both SEO and reader value.

Your outline must:
1. Target the primary keyword naturally in H1, at least two H2s, and the meta description
2. Address the user's full search intent — not just the keyword
3. Follow the inverted pyramid: most important information first
4. Include a logical section flow that builds on each previous section
5. Suggest one primary CTA aligned to the commercial intent of the topic

Primary keyword: KEYWORD
Brand voice: BRAND_VOICE
Relevant knowledge context: KNOWLEDGE_CHUNKS

Return ONLY a JSON object, no markdown, no explanation:
{"title": "H1 title under 65 chars", "meta_description": "150-160 chars with keyword", "word_count_target": 1800, "content_angle": "unique angle", "cta": "call to action", "outline": [{"h2": "Section Title", "detail": "what to cover in 2 sentences", "h3s": []}, {"h2": "Another Section", "detail": "what to cover", "h3s": ["Subsection A"]}]}

Example:
{"title": "10 Best AI Marketing Tools in 2025", "meta_description": "Discover the top AI marketing tools that save time and boost ROI.", "word_count_target": 1800, "content_angle": "Practical guide for non-technical marketers", "cta": "Start your free trial", "outline": [{"h2": "What Are AI Marketing Tools?", "detail": "Define AI marketing tools and explain why they matter for modern teams.", "h3s": []}, {"h2": "Top 10 AI Marketing Tools", "detail": "Review each tool with pros, cons, and pricing.", "h3s": ["Content Creation", "SEO Tools"]}]}

Do not write the article. Return the JSON only.\
""",

    "article_writer": """\
You are writing one section of an SEO-optimized article. Write only the HTML body of this section.

Rules:
- Write in active voice, sentences under 25 words
- Use practical examples, not just theory
- Short paragraphs (3-4 sentences max), use bullet lists for 4+ items
- No filler phrases: "In today's world", "It goes without saying"
- End with a concrete takeaway the reader can act on
- Do NOT include the H2 heading — it will be added automatically
- Return ONLY the HTML (p tags, ul/ol, em, strong). No JSON. No markdown. No explanation.

Section to write: SECTION_TITLE
Article title: ARTICLE_TITLE
Primary keyword: KEYWORD
Brand voice: BRAND_VOICE
Section outline: SECTION_OUTLINE
Relevant knowledge: KNOWLEDGE_CHUNKS
Internal link placeholders: INTERNAL_LINKS
Target word count for this section: WORD_COUNT words

LEARNED_PREFERENCES\
""",

    "linkedin_agent": """\
You are writing a LinkedIn post that drives engagement and positions the author as
a credible expert in their field.

LinkedIn post formula:
1. Hook (line 1): bold statement, surprising statistic, or provocative question — no fluff
2. Setup (lines 2-4): expand on the hook, establish why this matters
3. Value (lines 5-12): the actual insight, lesson, or story — be specific, not generic
4. Takeaway (lines 13-15): one clear, actionable conclusion the reader can apply today
5. Call to action (final line): question to drive comments OR soft CTA to relevant content

Formatting rules:
- Single-sentence paragraphs for the hook and takeaway
- Max 2-sentence paragraphs elsewhere — white space is engagement
- No hashtag stuffing: 2-3 relevant hashtags maximum, placed at the end
- Emojis: optional, use sparingly (0-2 max) — only if they add clarity
- No "I'm excited to share" or "Thrilled to announce" openers

Voice: professional but human. Write like a smart colleague talking, not a press release.

Source content:
SOURCE_CONTENT

Primary keyword: PRIMARY_KEYWORD
Target audience: TARGET_AUDIENCE

Return ONLY a JSON object, no markdown, no explanation:
{"post_text": "full linkedin post text here", "hashtags": ["aimarketing", "seo"], "estimated_reach_tier": "medium"}

estimated_reach_tier must be one of: low, medium, high

Example:
{"post_text": "Most marketers are wasting 60% of their content budget.\n\nHere is why...\n\nThe real issue is not the tools — it is the strategy.", "hashtags": ["contentmarketing", "aitools"], "estimated_reach_tier": "high"}\
""",

    "video_script_agent": """\
You are writing a video script for a short-form educational marketing video (3-5 minutes).

Script structure:
1. Hook (0-15s): one sentence that stops the scroll — bold claim or surprising question
2. Intro (15-30s): who this is for and what they will learn
3. Main sections (30s-4min): 4-6 scenes, each covering one key point
4. CTA (final 20s): one clear action for the viewer to take

Scene format for each section:
- Scene number and title
- Narration: exact words the presenter says (natural, conversational)
- Visual: what appears on screen (slides, screen recordings, animations, talking head)
- B-roll notes: supplementary footage suggestions
- Duration: estimated seconds

Script rules:
- Write narration how people actually speak — short sentences, contractions OK
- One idea per scene — do not cram multiple points
- Visual descriptions must be specific enough for a video editor to execute
- No filler phrases: "In this video I will show you..."

Source content:
SOURCE_CONTENT

Primary keyword: PRIMARY_KEYWORD
Target video length: TARGET_DURATION seconds

Return ONLY a JSON object, no markdown, no explanation:
{"title": "video title", "total_duration_seconds": 180, "scenes": [{"scene_number": 1, "title": "Hook", "narration": "text", "visual": "description", "b_roll": "notes", "duration_seconds": 15}], "cta": "call to action text"}

Example scene:
{"scene_number": 1, "title": "Hook", "narration": "You are spending 10 hours a week on marketing tasks AI can do in 10 minutes.", "visual": "Text overlay on dark background: 10 hours → 10 minutes", "b_roll": "Time-lapse of person working at desk", "duration_seconds": 12}\
""",

    "lead_magnet_agent": """\
You are creating a high-value lead magnet that captures email addresses by solving a specific problem.

Lead magnet types (pick the best fit for the keyword):
- Checklist: step-by-step action items (best for process topics)
- Template: fill-in-the-blank framework (best for strategy topics)
- Mini-guide: 5-7 page PDF with practical depth (best for educational topics)
- Swipe file: collection of examples/scripts (best for copywriting topics)

Structure requirements:
1. Title: outcome-focused, under 60 chars — what the reader GETS, not what it IS
2. Subtitle: one sentence expanding on the value promise
3. Introduction: 2-3 sentences on the problem this solves
4. Sections: 4-8 sections, each with a title and 3-5 actionable bullet points
5. Bonus tip: one advanced insight that makes it feel premium
6. CTA page: what to do next (visit site, book call, etc.)

Quality bar:
- Every bullet must be actionable — no vague advice
- Include specific numbers, tools, or examples where possible
- Reader should be able to use this immediately without buying anything

Source content:
SOURCE_CONTENT

Primary keyword: PRIMARY_KEYWORD
Target audience: TARGET_AUDIENCE

Return ONLY a JSON object, no markdown, no explanation:
{"title": "lead magnet title", "subtitle": "value promise", "format": "checklist/template/mini-guide/swipe-file", "introduction": "problem statement", "sections": [{"title": "section title", "bullets": ["actionable point 1", "actionable point 2"]}], "bonus_tip": "advanced insight", "cta": "next step"}

Example:
{"title": "The AI Marketing Checklist", "subtitle": "50 tasks you can automate starting today", "format": "checklist", "introduction": "Most marketing teams waste 60% of their time on tasks AI handles better.", "sections": [{"title": "Content Creation", "bullets": ["Use Claude Sonnet for first drafts", "Generate 10 headline variants in 30 seconds"]}], "bonus_tip": "Batch all AI tasks on Monday mornings for 3x efficiency.", "cta": "Download our full AI marketing toolkit at vikas.ai"}\
""",

    "image_creator_agent": """\
You are writing a detailed image generation prompt for a marketing visual.

The prompt will be sent directly to DALL-E 3 or Midjourney to generate an image.
Write a prompt that produces a professional, brand-appropriate marketing image.

Prompt requirements:
1. Subject: what is in the image (people, objects, abstract concepts)
2. Style: photorealistic / flat illustration / 3D render / infographic
3. Mood: the emotional tone (professional, energetic, calm, innovative)
4. Composition: foreground, background, focal point
5. Colors: primary palette (avoid neon unless brand uses it)
6. Text overlays: if any text should appear in the image
7. Negative prompt: what to avoid (clutter, watermarks, distorted faces)

Marketing image rules:
- No copyrighted logos or brand names
- Faces should be diverse and professional
- Avoid clichéd stock photo poses (handshakes, pointing at whiteboards)
- Prefer clean, modern aesthetics that work at multiple sizes

Article title: ARTICLE_TITLE
Primary keyword: PRIMARY_KEYWORD
Image use case: IMAGE_USE_CASE

Return ONLY a JSON object, no markdown, no explanation:
{"prompt": "detailed DALL-E prompt", "negative_prompt": "what to avoid", "style": "photorealistic/illustration/3d", "aspect_ratio": "16:9 or 1:1 or 9:16", "alt_text": "accessibility description"}

Example:
{"prompt": "A focused professional marketer at a clean desk reviewing analytics on a modern laptop, soft natural lighting, minimalist office background, blue and white color scheme, photorealistic", "negative_prompt": "clutter, watermarks, distorted faces, neon colors", "style": "photorealistic", "aspect_ratio": "16:9", "alt_text": "Marketing professional reviewing AI analytics dashboard"}\
""",

    "newsletter_agent": """\
You are writing a marketing email newsletter that educates subscribers and drives clicks.

Newsletter formula:
1. Subject line: curiosity-driven, under 50 chars, no spam words (FREE, CLICK NOW, etc.)
2. Preview text: 90-110 chars, expands on subject line, creates urgency or curiosity
3. Opening (2-3 sentences): personal, conversational hook — like writing to one person
4. Body (3-5 short sections): each section one insight or tip, max 3 sentences each
5. CTA button: one clear action — "Read the full guide", "Try it free", etc.
6. Sign-off: short, human, first-name style

Formatting rules:
- Short paragraphs — 2-3 sentences max, white space is readability
- No wall of text — newsletters are scanned, not read
- One CTA only — multiple links kill conversion
- Plain language — grade 8 reading level
- No "I hope this email finds you well" openers

Voice: friendly expert. Like a smart colleague sharing something useful, not a brand blasting promotions.

Source content:
SOURCE_CONTENT

Primary keyword: PRIMARY_KEYWORD
Target audience: TARGET_AUDIENCE

Return ONLY a JSON object, no markdown, no explanation:
{"subject_line": "under 50 chars", "preview_text": "90-110 chars", "body": "full newsletter HTML", "cta_text": "button text", "estimated_open_rate_tier": "low/medium/high"}

estimated_open_rate_tier must be one of: low, medium, high

Example:
{"subject_line": "5 AI tools saving marketers 10h/week", "preview_text": "Most teams don't know these exist. Here is what we found.", "body": "<p>Hey,</p><p>Last week I tested 20 AI marketing tools...</p>", "cta_text": "Read the full breakdown", "estimated_open_rate_tier": "high"}\
""",

    "twitter_agent": """\
You are writing a Twitter/X thread that drives engagement and grows an audience.

Thread formula:
1. Tweet 1 (hook): bold claim, surprising stat, or strong opinion — max 220 chars, no fluff
2. Tweets 2-4 (setup): expand on the hook, why this matters, one idea per tweet
3. Tweets 5-8 (value): the actual insights — numbered tips, lessons, or story beats
4. Tweet 9 (takeaway): one clear actionable conclusion
5. Tweet 10 (CTA): follow for more OR link to the full article

Formatting rules:
- Each tweet max 280 characters
- Number tweets: "1/" "2/" etc
- Short punchy sentences — Twitter rewards scannability
- 1-2 emojis per tweet maximum, only if they add clarity
- No hashtag stuffing: 2-3 hashtags on the final tweet only
- No "A thread:" opener — just start with the hook

Voice: direct, confident, slightly provocative. Opinions are fine.

Source content:
SOURCE_CONTENT

Primary keyword: PRIMARY_KEYWORD
Target audience: TARGET_AUDIENCE

Return ONLY a JSON object, no markdown, no explanation:
{"tweets": ["1/ hook tweet", "2/ second tweet"], "hashtags": ["aimarketing", "seo"], "estimated_reach_tier": "medium"}

estimated_reach_tier must be one of: low, medium, high
tweets must be a list of strings, each under 280 characters

Example:
{"tweets": ["1/ 90% of content never gets read.", "2/ Here is why most marketers are wasting their budget...", "3/ The fix is simpler than you think."], "hashtags": ["contentmarketing", "aitools"], "estimated_reach_tier": "high"}\
""",

    "brand_voice_keeper": """\
You are enforcing brand voice guidelines during content review. Your job is to identify
deviations from the established brand voice and suggest specific corrections.

Review dimensions:
1. Tone consistency — does the content match the defined tone (formal/casual/authoritative/friendly)?
2. Vocabulary — are banned phrases present? Are preferred terms used?
3. Sentence structure — does the rhythm and complexity match the style guide?
4. Perspective — is the correct POV used (we/you/they) as specified?
5. Values alignment — does the content reflect the brand's stated values and positioning?

For each issue found, provide:
- location: quote the exact phrase or sentence that violates the guidelines
- violation_type: tone | vocabulary | structure | perspective | values
- severity: minor | moderate | major
- suggestion: the corrected version

If the content passes all checks, return an empty issues array with a score of 1.0.

Brand voice definition: {brand_voice}
Content to review: {content}
Content type: {content_type}

Return JSON: {{ "score": 0.0-1.0, "issues": [...], "overall_assessment": "one sentence" }}
""",

    # ── Sentiment analyser prompts ────────────────────────────────────────────
    # Registry keys use the dotted format: sentiment_analyser.<name>.<version>
    # Agents load these via PromptRegistry().get(key, db).

    "sentiment_analyser.polarity_classifier_en.v1": """\
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
\"\"\"
MENTION_TEXT
\"\"\"

JSON output:
""",

    "sentiment_analyser.polarity_classifier_ta.v1": """\
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
\"\"\"
MENTION_TEXT
\"\"\"

JSON output:
""",

    "sentiment_analyser.polarity_batch.v1": """\
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
- Apply sarcasm detection: sarcastic praise -> negative
- Return one object per input, preserving order

CONTEXT:
Scheme reference: SCHEME_NAME
District reference: DISTRICT_NAME

INPUTS (JSON array):
MENTION_BATCH_JSON

JSON output:
""",

    "sentiment_analyser.theme_discovery.v1": """\
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
- Only surface themes that appear in >= 3 mentions in the sample
- Themes must be specific enough to be actionable, not so specific they apply to one mention
- A theme is "novel" if no existing taxonomy entry covers it semantically
- recommend_add_to_taxonomy = true only if frequency is meaningful AND theme is distinct
- Examples: "delayed pension disbursement" is good; "people are unhappy" is too vague

EXISTING THEME TAXONOMY:
EXISTING_THEMES_JSON

SAMPLE MENTIONS (JSON array, each with id, text, polarity):
SAMPLE_MENTIONS_JSON

JSON output:
""",

    "sentiment_analyser.theme_classifier.v1": """\
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
- Include a theme only if confidence >= 0.6
- Maximum 5 themes per mention
- evidence_quote must be a substring (or close paraphrase under 15 words) of the original mention
- If nothing clearly matches, return empty array and explain in no_match_reason

THEME TAXONOMY:
THEME_TAXONOMY_JSON

MENTION TEXT:
\"\"\"
MENTION_TEXT
\"\"\"

Context: scheme=SCHEME_NAME, district=DISTRICT_NAME, language=DETECTED_LANGUAGE

JSON output:
""",

    "sentiment_analyser.entity_extractor.v1": """\
You are extracting entities and factual claims from a political mention about an Indian government scheme. Be precise. Do not infer beyond what is stated.

Output strict JSON only. No prose. No markdown fences.

Schema:
{
  "schemes_mentioned": [<list of scheme names exactly as they appear in text>],
  "districts_mentioned": [<list of place names exactly as they appear>],
  "persons_mentioned": [
    {
      "name": "<as appearing>",
      "role_if_stated": "<e.g. MLA, Mayor, beneficiary or empty string>",
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
\"\"\"
MENTION_TEXT
\"\"\"

Source type: SOURCE_TYPE
Language: DETECTED_LANGUAGE

JSON output:
""",

    "sentiment_analyser.spike_analyzer.v1": """\
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
  "amplification_signals": [<list of signals e.g. "identical phrasing across accounts">],
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
- Avoid recommending content production for "monitor_only"; that is the point of it

CONTEXT:
Scheme: SCHEME_NAME
District: DISTRICT_NAME
Window analyzed: WINDOW_START to WINDOW_END
Baseline (rolling 7-day avg): BASELINE_STATS
Current window stats: CURRENT_STATS

TOP MENTIONS DRIVING THE SPIKE (JSON array):
SPIKE_MENTIONS_JSON

JSON output:
""",

    "sentiment_analyser.source_credibility.v1": """\
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
""",
}


async def seed(dry_run: bool = False, update: bool = False) -> None:
    registry = PromptRegistry()

    # Prompts are global — use a placeholder org_id just to open a session.
    # The prompts table has no org_id column; this is only needed for session context.
    async with org_session("00000000-0000-0000-0000-000000000000") as db:
        for agent_name, template in PROMPTS.items():
            already_exists = False
            try:
                await registry.get(agent_name, db)
                already_exists = True
            except Exception:
                pass

            if already_exists and not update:
                print(f"  SKIP  {agent_name!r} — active prompt already exists (use --update to replace)")
                continue

            if dry_run:
                action = "would update" if already_exists else "would insert version 1"
                print(f"  DRY   {agent_name!r} — {action}")
                continue

            version = await registry.set(agent_name, template.strip(), db)
            action = "updated to" if already_exists else "inserted"
            print(f"  SEED  {agent_name!r} — {action} version {version}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    update = "--update" in sys.argv
    if dry_run:
        print("Dry run — no changes will be made.\n")
    asyncio.run(seed(dry_run=dry_run, update=update))
    print("\nDone.")
