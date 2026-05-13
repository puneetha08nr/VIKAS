# How Vikas Works

## The Content Pipeline

### Step 1: Keyword Research
You enter a seed keyword like "ai marketing tools". The keyword_research agent calls DataForSEO and returns 500+ related keywords with real search volumes, keyword difficulty, and CPC data. No guessing — real market data.

### Step 2: Keyword Validation
The keyword_validator agent filters keywords using hard rules:
- Volume must be above 100 searches/month
- Keyword difficulty (KD) below 8 out of 10
- Not navigational intent (people searching for a specific website)
- Commercial or informational intent preferred

### Step 3: Opportunity Scoring
The opportunity_scorer agent ranks validated keywords by combining 4 scores:
- Search score: how much people search for it
- Competitive gap score: how weak competitors are
- Trend score: is it growing or declining
- Engagement score: will people click and share

Keywords with high composite scores become opportunities.

### Step 4: Content Direction
The content_director agent reads an opportunity and decides what formats to produce — article, LinkedIn post, Twitter thread, newsletter — based on format fit scores.

### Step 5: Article Planning
The article_planner agent generates a structured outline:
- SEO-optimized title
- Meta description
- H2 sections with descriptions
- H3 subsections
- Target word count
- Content angle
- Call to action

You can review and edit this outline before writing starts.

### Step 6: Article Writing
The article_writer agent takes the approved outline and writes each H2 section separately. It uses:
- Your brand voice guidelines
- Knowledge base (RAG) for company-specific facts
- Internal link suggestions
- SEO keyword placement rules

### Step 7: Social Content
After the article is written:
- linkedin_agent creates a LinkedIn post from the outline (faster, fewer tokens)
- twitter_agent creates a 10-tweet thread from the outline
- newsletter_agent creates an email newsletter from the full article

### Step 8: Human Review
All content lands in the review queue. You can approve, edit, or reject each piece. The system learns from your edits through the preference_learner agent — the 11th article is noticeably better than the 1st.

### Step 9: Publishing
Approved articles go to wordpress_publisher which pushes them to your WordPress site via the REST API. Social posts can be published to their respective platforms once API credentials are configured.

## Auto Mode
Auto Mode runs every night at 2 AM UTC and:
1. Collects trending topics
2. Monitors competitors
3. Scores opportunities
4. Selects top N opportunities based on daily caps
5. Runs the full content pipeline
6. Notifies your team in the morning with a review queue ready

## The Preference Learning Loop
Every time you approve, edit, or reject content:
- The feedback is stored in content_feedback table
- preference_learner agent runs weekly
- It extracts patterns from your edits
- Future content automatically incorporates your preferences
- Approve 10 drafts — the 11th is noticeably better
