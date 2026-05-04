# Vikas

A multi-agent AI platform that automates the entire marketing operation — keyword research, content creation, competitor intel, video production, and publishing — while you sleep.


# add to your commit habit:
./scripts/end_session.sh   # copy prompt → paste into Claude Code → update files
git add CLAUDE.md ISSUES_AND_FIXES.md
git commit -m "update: session notes and agent status"


Context: building Vikas, a 45-agent AI marketing platform. 
CLAUDE.md is attached. Current state: keyword_research agent done, 
moving to keyword_validator. Stack: FastAPI, PostgreSQL+pgvector, 
Celery, Next.js, Ollama for dev.

[IMPL] docker logs vikas-worker-1 shows this error...
[ARCH] why do we need RLS when we already have org_id filtering?
[DOUBT] what does idempotent mean in plain terms?
[EVAL] how do we verify keyword_validator is working?
