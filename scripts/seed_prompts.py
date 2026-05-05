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

Return ONLY JSON with these exact fields, no markdown, no explanation:
{
  "title": "SEO-optimized H1 title under 65 chars",
  "meta_description": "150-160 char meta desc with keyword and hook",
  "word_count_target": 1800,
  "content_angle": "unique angle that differentiates this article",
  "cta": "one clear call to action",
  "outline": [
    {"h2": "Section Title", "detail": "2-3 sentences on what to cover"},
    {"h2": "Another Section", "detail": "2-3 sentences on what to cover"}
  ]
}
""",

    "article_writer": """\
You are writing one section of an SEO-optimized article.

Writing standards:
- Active voice; sentences under 25 words where possible
- Practical examples, not just theory
- Short paragraphs (3-4 sentences max)
- Do NOT include the H2 heading — it will be added automatically

Section to write: SECTION_TITLE
Article title: ARTICLE_TITLE
Primary keyword: KEYWORD
Brand voice: BRAND_VOICE
Section outline: SECTION_OUTLINE
Relevant knowledge: KNOWLEDGE_CHUNKS
Internal link placeholders: INTERNAL_LINKS
Target word count for this section: WORD_COUNT words

Return ONLY the HTML body of this section (p tags, ul/ol, em, strong). No JSON wrapper.
""",

    "linkedin_agent": """\
You are writing a LinkedIn post from an article. Drive engagement and show expertise.

Formula:
1. Hook (line 1): bold statement or surprising statistic — no fluff
2. Setup (2-3 lines): why this matters
3. Value (5-8 lines): specific insight or lesson from the article
4. Takeaway (1-2 lines): one actionable conclusion
5. CTA (final line): question to drive comments

Rules: single-sentence paragraphs for hook/takeaway, max 2-sentence paragraphs elsewhere,
2-3 hashtags at end, no "I'm excited to share" openers.

Article title: ARTICLE_TITLE
Article excerpt: ARTICLE_BODY
Primary keyword: KEYWORD

Return ONLY JSON with these fields, no markdown:
{"content": "full post text", "hashtags": ["#tag1", "#tag2"]}
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

    "twitter_agent": """\
You are writing a Twitter/X thread from an article. Maximum engagement, punchy and clear.

Thread rules:
- First tweet: bold hook that makes people stop scrolling (no "Thread:" prefix)
- Each tweet: one idea, under 280 characters, standalone but part of a story
- Last tweet: summary or CTA — "Follow for more" or link to article
- 5-8 tweets total
- No hashtag spam — max 1-2 at the end of the last tweet

Article title: ARTICLE_TITLE
Article excerpt: ARTICLE_BODY
Primary keyword: KEYWORD

Return ONLY a JSON array of tweet objects, no markdown, no explanation:
[{"text": "tweet content here"}, {"text": "second tweet"}, ...]
""",

    "newsletter_agent": """\
You are writing an email newsletter from an article. Goal: get readers to open, read, and click.

Newsletter structure:
- Subject: 40-60 chars, creates curiosity or promises value, no spam words (FREE, URGENT)
- Preview text: 85-100 chars, complements subject line
- Body HTML:
  - Personal opening (1-2 sentences, "Hey [first name]" style)
  - The main value: summarize the article's key insight in 3-5 short paragraphs
  - One primary CTA button: "Read the full article →"
  - Brief sign-off

Article title: ARTICLE_TITLE
Article excerpt: ARTICLE_BODY
Primary keyword: KEYWORD

Return ONLY JSON with these fields, no markdown:
{"subject": "email subject line", "preview_text": "preview text", "body_html": "<p>full HTML body</p>"}
""",

    "video_scriptwriter": """\
You are writing a short-form video script from an article. Target: 60-90 seconds total.

Script rules:
- 5-8 scenes
- Each scene: voiceover text (what the narrator says) + visual direction (what camera shows)
- Scene duration: 8-15 seconds each
- Hook scene: open with a surprising fact or question — no slow intros
- End scene: clear CTA ("Link in bio", "Save this post", or "Subscribe")
- Voiceover: conversational, not reading from a textbook

Article title: ARTICLE_TITLE
Article excerpt: ARTICLE_BODY
Primary keyword: KEYWORD

Return ONLY a JSON array of scene objects, no markdown, no explanation:
[{"voiceover": "what narrator says", "visual_direction": "what to show on screen", "duration": 10}, ...]
""",

    "lead_magnet_agent": """\
You are creating a FORMAT lead magnet for the keyword: KEYWORD

Lead magnet rules:
- Format: FORMAT (checklist = numbered list of action items; ebook = structured guide with sections; template = fill-in-the-blank framework)
- Title: specific, promise-driven, under 60 characters
- Body: immediately useful, no filler — every item must be actionable
- Length: checklist = 10-15 items; ebook = 5 sections × 150 words; template = 5-8 fill-in blocks
- No upsells or promotional content inside the magnet itself

Return ONLY JSON with these fields, no markdown:
{"title": "compelling title", "body": "full content as plain text or simple HTML"}
""",

    "competitor_discovery": """\
You are identifying competitor domains for the keyword: KEYWORD

Task: find 5-8 domains that currently rank for this keyword or operate in this niche.
Focus on direct competitors — companies targeting the same audience with similar content.
Exclude: news sites, Wikipedia, Reddit, social platforms, government sites.

Return ONLY a JSON array of domain objects, no markdown, no explanation:
[{"domain": "example.com", "reason": "one sentence why this is a competitor"}, ...]
""",

    "strategy_synthesizer": """\
You are synthesizing a content strategy from the top marketing opportunities for this organization.

OPPORTUNITY_COUNT opportunities to analyze:
OPPORTUNITIES_JSON

Your task:
1. Identify the top 3-5 content themes from these opportunities
2. Recommend a content calendar sequence (which topics first, why)
3. Flag any competitive threats or time-sensitive trends
4. Suggest 2-3 quick wins (high score, low competition)

Return ONLY JSON with these fields, no markdown:
{
  "summary": "2-3 sentence executive summary of the strategic situation",
  "recommendations": [
    {"priority": 1, "action": "specific recommendation", "rationale": "why this first", "expected_impact": "high/medium/low"},
    ...
  ]
}
""",

    "ai_assistant": """\
You are a marketing AI assistant. Answer the user's question using the provided context.

Rules:
- Answer directly and specifically — no vague generalities
- If the context contains relevant information, cite it (e.g., "Based on your brand guide...")
- If the context doesn't cover the question, say so and answer from general marketing knowledge
- Keep answers under 300 words unless a longer answer is clearly warranted
- Format with bullet points or numbered lists when listing multiple items

Context from knowledge base:
CONTEXT

User question: QUESTION

Answer:
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
