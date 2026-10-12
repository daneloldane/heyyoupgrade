# HeyYoUpgrade: free hosting, step by step

This puts the site online for free on GitHub Pages and makes it check for new deals
every 10 minutes by itself. You do not need to install anything. Everything is done
in your web browser. It takes about 15 minutes.

## What is in this folder

| File | What it does |
| --- | --- |
| `index.html` | The website |
| `deals.json` | The list of deals the website shows. The fetcher rewrites it |
| `sources.json` | Where the fetcher looks for deals. You can edit it |
| `scripts/fetch_deals.py` | The fetcher |
| `update.yml` | The schedule that runs the fetcher every 10 minutes |

## Step 1: Make a free GitHub account

Go to https://github.com/signup and sign up. Skip this if you already have one.

## Step 2: Create a repository

1. Click the **+** at the top right, then **New repository**.
2. Name it `heyyoupgrade`.
3. Choose **Public**. This matters: public repositories get unlimited free automation time.
4. Tick **Add a README file**, then click **Create repository**.

## Step 3: Upload the files

1. Unzip the download on your computer.
2. In your new repository click **Add file**, then **Upload files**.
3. Drag in `index.html`, `deals.json`, `sources.json` and the whole `scripts` folder.
   Do not upload `update.yml` here. It needs a special place (next step).
4. Click **Commit changes**.

## Step 4: Add the schedule file

1. Click **Add file**, then **Create new file**.
2. In the name box type exactly: `.github/workflows/update.yml`
   (typing each `/` creates the folders for you).
3. Open `update.yml` from the unzipped folder in any text editor, select everything,
   copy it and paste it into the big box on GitHub.
4. Click **Commit changes**, then **Commit changes** again.

## Step 5: Turn on the website

1. Go to **Settings**, then **Pages** (left menu).
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.

## Step 6: Let the schedule save its results

1. Go to **Settings**, then **Actions**, then **General**.
2. Scroll to **Workflow permissions**, choose **Read and write permissions**, click **Save**.

## Step 7: Run it for the first time

1. Click the **Actions** tab.
2. Click **Update deals** in the left list, then **Run workflow**, then the green **Run workflow** button.
3. Wait about a minute until you see a green tick.
4. Your site is now live at `https://YOUR-USERNAME.github.io/heyyoupgrade/`

From now on it runs by itself every 10 minutes. If nothing new was found, it does not
redeploy, so it stays quiet.

## Check that it is working

Open the site and scroll to **Where prices come from**. Each source shows
**Working**, **Failing** or **Not set up**, with the reason. A green "Live" bar at
the top means real deals are loaded. A yellow "Example listings" bar means no real
deals have been found yet.

## Sections and Bundle Basket

The purple bar has a section for each part type, plus the Bundle Basket on the right.
Part lists come from the **Top 10 by category** source in `sources.json`. Each entry in its
`pages` list is a retailer category page. The fetcher reads the first 10 products in the
shop's own order and refreshes them every 10 minutes. If a page cannot be read, its last
saved list stays on screen, and **Where prices come from** says which page failed.
To add a page, copy one entry and change `url`, `cat` (gpu, cpu, memory, motherboard,
psu, case or cooling), `retailer` and `rank_by`.

The basket stores your pins in your own browser. It is not shared between devices.

## Adding more sources

**Any RSS or Atom feed.** Open `sources.json` on GitHub, click the pencil icon and add:

```json
{ "name": "My feed", "type": "rss", "url": "https://example.com/feed.rss", "enabled": true }
```

The fetcher keeps posts that look like a gaming PC or a parts bundle and have a
price in pounds.

**Retailer product feeds through Awin (the reliable route to many retailers).**
1. Apply as a publisher at https://www.awin.com (free).
2. Apply to each retailer's programme you want. Each one approves you separately.
3. In Awin use **Create-a-Feed** for that retailer, choose CSV, and copy the feed URL.
4. In GitHub go to **Settings, Secrets and variables, Actions, New repository secret**.
   Name it `AWIN_FEED_1` and paste the URL as the value.
   Use `AWIN_FEED_2` for a second feed. Never put these URLs in a normal file,
   because they contain your private key.
5. Run the workflow again from the **Actions** tab.

## Things to know

- **Timing.** GitHub's 10-minute schedule is best effort. At busy times a run can start
  5 to 30 minutes late. Deals appear within minutes of a post, not within seconds.
- **Pausing.** GitHub switches off scheduled runs in a repository with no activity for
  60 days. If that happens, open the **Actions** tab and click **Enable workflow**.
- **Reddit.** Reddit blocks the plain feed from GitHub's servers, so the site uses Reddit's
  official API instead. It is free but needs a one-off setup:
  1. Log in to Reddit, open https://www.reddit.com/prefs/apps and click **create another app**.
  2. Name it `heyyoupgrade`, choose **script**, set the redirect URI to `http://localhost`, and create it.
  3. Copy the short code under the app name (the client id) and the **secret**.
  4. In GitHub go to **Settings, Secrets and variables, Actions, New repository secret**.
     Add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`.
  5. Run the workflow from the **Actions** tab.
  Reddit's terms limit commercial use of its data. If the site will earn affiliate money,
  check them first. Posts about single parts appear in the matching section as "Community deal".
- **Accuracy.** Specs are read from post titles by pattern matching, so a few will be
  wrong or blank. The page always links to the original post or retailer page so
  people can check before they buy.
- **Affiliate links.** In the UK you must make it clear when links earn you commission.
  Add a short line to the footer when you start using them.
