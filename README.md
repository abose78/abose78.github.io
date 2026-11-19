# Arindam Bose – Resume

Live site: https://abose78.github.io

To update: replace `Arindam_Bose_Resume.docx` (same filename) via Add file → Upload files → Commit.
GitHub Actions rebuilds the web page from the Word file in about a minute.

Keep these headings in the Word file: Professional Summary, Technical Skills, Experience, Education.
Highlight numbers at the top of the page are in `build/stats.json`.

## Update from LinkedIn

Upload Profile.pdf (LinkedIn → More → Save to PDF) or the LinkedIn data export .zip into the `linkedin/` folder. GitHub rewrites the Word file's Experience and Education from LinkedIn, then rebuilds the site. See `linkedin/README.md`.

## Skill search

The "Search my skills" sidebar runs an AI model (all-MiniLM-L6-v2) in the visitor's browser; nothing is sent to a server.
Metrics are computed at build time from the Word file into `search-index.json`.
Add or adjust skills, aliases and related techs in `build/skills_taxonomy.json`.
