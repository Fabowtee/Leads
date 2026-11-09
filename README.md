# Daily Lead Research

Finds new business leads every day and saves them in the `leads` folder.

## Setup (one time)
1. Edit the 3 files in `config/`: `icp.md`, `excluded.csv`, `examples.csv`. Change `config.yaml` if you want more or fewer leads.
2. In GitHub: Settings > Secrets and variables > Actions > New repository secret.
   Name: `ANTHROPIC_API_KEY`  Value: your key from console.anthropic.com
3. Go to the Actions tab > "Daily lead research" > Run workflow, to test it.

## Results
- `leads/YYYY-MM-DD.csv`: today's leads
- `leads/all_leads.csv`: every lead so far (used to avoid repeats)
- `leads/run_log.jsonl`: what happened each day
