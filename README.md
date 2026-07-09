# LeetCode GitHub Sync

This repository can automatically archive your LeetCode submissions into GitHub.

It uses a GitHub Actions workflow that runs every hour, fetches your LeetCode submissions, and commits any new ones into this repo.

## What Gets Stored

- Every synced submission is archived under `submissions/<problem-slug>/`.
- Accepted submissions also update `solutions/<problem-slug>/<problem-slug>.<ext>` with the latest accepted version.
- Submission metadata is saved beside each archived file as JSON.

## Setup

1. Create a GitHub repository and push this folder to it.
2. In GitHub, open the repository settings.
3. Go to `Secrets and variables` -> `Actions` -> `New repository secret`.
4. Add these secrets:

| Secret | Value |
| --- | --- |
| `LEETCODE_SESSION` | Your `LEETCODE_SESSION` browser cookie from `leetcode.com` |
| `LEETCODE_CSRF_TOKEN` | Your `csrftoken` browser cookie from `leetcode.com` |

5. Open the `Actions` tab and enable workflows if GitHub asks.
6. Run `Sync LeetCode submissions` manually once from the Actions tab.

After that, the workflow runs hourly.

## Getting The Cookie Values

In your browser, sign in to LeetCode, then open developer tools:

- Chrome or Edge: `F12` -> `Application` -> `Cookies` -> `https://leetcode.com`
- Firefox: `F12` -> `Storage` -> `Cookies` -> `https://leetcode.com`

Copy the values for:

- `LEETCODE_SESSION`
- `csrftoken`

Keep these secret. They allow access to your LeetCode account session.

## Configuration

Optional repository variables or workflow environment values:

| Name | Default | Description |
| --- | --- | --- |
| `LEETCODE_SYNC_STATUSES` | `all` | Comma-separated statuses to archive, for example `Accepted,Wrong Answer`, or `all`. |
| `LEETCODE_PAGE_LIMIT` | `20` | Submissions fetched per LeetCode request. |
| `LEETCODE_MAX_PAGES` | empty | Optional safety cap for pages fetched per run. |
| `LEETCODE_BASE_URL` | `https://leetcode.com` | Change only if you know you need another LeetCode host. |

To archive only accepted submissions, set `LEETCODE_SYNC_STATUSES` to `Accepted` in `.github/workflows/leetcode-sync.yml`.
