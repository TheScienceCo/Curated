# Raw Job Data

This directory is for storing raw job recruiting advertisements and emails that you want to import into the Job Intelligence Agent.

## How to Use

### Option 1: Frontend Bulk Import (Recommended)
1. Go to the Dashboard
2. Click "+ Bulk import" button
3. Paste job descriptions in the modal textarea
4. Separate multiple jobs with blank lines
5. Click "Import"

The system will:
- Extract structured data from each job
- Score each job against your profile
- Skip duplicates and jobs below the scoring threshold (40)
- Show you a summary of results

### Option 2: Direct File Storage
1. Save raw job text files here (e.g., `amazon-sde-2024.txt`)
2. Use the bulk import endpoint via API:
```bash
curl -X POST http://localhost:8000/api/jobs/bulk-import \
  -H "Content-Type: application/json" \
  -d '{"jobs": ["<raw job text 1>", "<raw job text 2>"]}'
```

## What Gets Processed

The extraction pipeline can handle:
- Full job postings (HTML or plain text)
- Email forwarded job ads
- LinkedIn job descriptions
- Manually written job descriptions
- Slack messages with job details

Any text format is fine — the system will extract:
- Company name
- Job title
- Location
- Salary/compensation
- Remote status
- Required/preferred skills
- Years of experience
- Clearance requirements
- And more...

## Scoring & Filtering

Jobs are automatically:
1. **Scored** against your profile using the 7-dimensional scoring system
2. **Deduped** (same company + title + location = duplicate)
3. **Filtered** (only jobs scoring ≥40 are saved)

Jobs below the threshold are discarded but the import result tells you how many were skipped.

## Example

If you paste:
```
Company: Acme Corp
Position: Senior Software Engineer
Location: San Francisco, CA
Salary: $180k-$220k
Remote: Hybrid
Required: Python, AWS, Docker
```

The system will:
- Extract all the fields
- Score it (e.g., 65/100 for your profile)
- Save it if it's your first Acme Corp Senior SDE, or skip if you already have one in the database
- Show you the result: "1 saved, 0 below threshold, 0 duplicates"

Then you can view it on the Dashboard, dive into detail scores, draft a response, or track your decision.
