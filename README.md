# Yankees Briefing

A public, static Yankees news dashboard that displays the five newest posts from Pinstripe Alley, Bronx Pinstripes, MLB Trade Rumors, Yanks Go Yard, and the official New York Yankees site.

## Refreshes

- GitHub Actions refreshes `data.json` daily at 13:00 UTC (9:00 AM EDT) and may be run manually from the **Actions** tab.
- The page itself is hosted through GitHub Pages.

## Local preview

```bash
python3 refresh.py
python3 server.py
# open http://127.0.0.1:8787/
```

The hosted GitHub Pages site is read-only; its data is refreshed by the workflow.

## Sources

Content, logos, and post imagery remain property of their respective publishers. Article cards link directly to the original source.
