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
5. Identify 3-5 internal linking opportunities (placeholder: [INTERNAL_LINK: topic])
6. Suggest one primary CTA aligned to the commercial intent of the topic

Outline format:
- Title (H1): keyword-optimized, <65 characters, compelling
- Meta description: 150-160 characters, includes keyword, has a hook
- Introduction (2-3 sentences): hook + preview of what reader will learn
- H2 sections (5-8): each with a brief description of what to cover (2-3 sentences)
  - Under complex H2s, add H3 subsections as needed
- Conclusion: summarize key takeaways + CTA
- Suggested internal links: list of 3-5 topics from our own content

Primary keyword: {primary_keyword}
Secondary keywords: {secondary_keywords}
Target word count: {word_count}
Content goal: {content_goal}
Audience expertise level: {audience_level}

Return a structured JSON outline. Do not write the article — outline only.
""",

    "article_writer": """\
You are writing a high-quality, SEO-optimized article that ranks well and genuinely
helps readers accomplish their goal.

Writing standards:
1. Use the primary keyword in the first 100 words and naturally throughout — no stuffing
2. Write in active voice; keep sentences under 25 words where possible
3. Use transition words between paragraphs to improve readability score
4. Every factual claim must be something you can substantiate — flag speculative statements
5. Include practical examples, not just theory
6. Format for scannability: short paragraphs (3-4 sentences max), use bullet lists for 4+ items
7. Do not use filler phrases: "In today's world", "It goes without saying", "As we all know"
8. End each major section with a concrete takeaway the reader can act on

SEO requirements:
- Primary keyword appears in: title, first paragraph, at least one H2, conclusion
- Secondary keywords woven in naturally (do not force them)
- Internal links inserted exactly where indicated in the outline
- Meta description included at the end as a separate field

Outline to follow: {outline}
Primary keyword: {primary_keyword}
Brand voice guidelines: {brand_voice}
Target word count: {word_count}

Return JSON with fields: title, meta_description, body (full HTML), word_count.
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

Source content: {source_content}
Key insight to highlight: {key_insight}
Target audience: {target_audience}
Author's perspective/angle: {author_angle}

Return JSON with fields: post_text, hashtags (list), estimated_reach_tier (low/medium/high).
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
