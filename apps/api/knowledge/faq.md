# Vikas FAQ

## What is Vikas?
Vikas is an AI-powered marketing platform that automates the entire marketing operation — keyword research, content creation, competitor analysis, and publishing. It runs 45+ specialized AI agents that work together to produce high-quality marketing content while you sleep.

## How does Vikas work?
Vikas works in a pipeline:
1. You enter a seed keyword (e.g. "ai marketing tools")
2. keyword_research agent finds 500+ related keywords using DataForSEO
3. keyword_validator filters and scores them
4. opportunity_scorer picks the best ones to write about
5. content_director triggers article_planner → article_writer
6. LinkedIn posts, Twitter threads, newsletters are generated automatically
7. Content goes to a human review queue — you approve before publishing
8. wordpress_publisher pushes approved content to your website

## How long does content generation take?
With Claude Sonnet or GPT-4o: ~2-3 minutes per full article
With local Mistral (free): ~15 minutes per article
Social posts (LinkedIn, Twitter): ~2-3 minutes additional

## Can I edit the AI-generated content?
Yes. All drafts go to a review queue first. You can:
- Edit the outline before writing starts (saves tokens)
- Edit the full article body after writing
- Approve or reject each piece of content
- The system learns from your edits and improves over time

## What content formats does Vikas generate?
- Full articles (1500-2000 words, HTML formatted)
- LinkedIn posts with hashtags
- Twitter/X threads (10 tweets)
- Email newsletters with subject line and preview text
- Video scripts with scene descriptions and B-roll notes
- Lead magnets (checklists, ebooks, templates)
- Image prompts for DALL-E 3

## Does Vikas publish automatically?
No. Nothing publishes without human approval. All content goes through a review queue first. This is a hard constraint — you always have final say. Once approved, the wordpress_publisher agent can push to WordPress automatically.

## What integrations does Vikas support?
- DataForSEO for keyword data
- Google Search Console for ranking data
- WordPress for publishing
- LinkedIn, Twitter, Newsletter (via API credentials)
- DALL-E 3 for image generation
- Slack for team notifications
- ZeptoMail/SMTP for email notifications

## Is my data secure?
Yes. Every organization's data is completely isolated using Row Level Security (RLS) at the PostgreSQL level. No data from one organization can be seen by another.

## Can multiple team members use Vikas?
Yes. Vikas supports organization-based multi-tenancy. You can add team members and they all see the same keywords, content, and opportunities.
