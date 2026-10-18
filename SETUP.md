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

## If updates fall behind

GitHub runs free scheduled jobs when it has spare capacity, so "every 10 minutes" can
become every few hours. The page says so when the last check is over 2 hours old.
To force a steady 10 minutes, use a free outside timer to start the workflow:

1. On GitHub open **Settings, Developer settings, Personal access tokens, Fine-grained tokens**.
   Create one for the `heyyoupgrade` repository only, with **Actions: Read and write**.
2. Sign up free at https://cron-job.org and create a job that runs every 10 minutes.
3. URL: `https://api.github.com/repos/YOUR-USERNAME/heyyoupgrade/actions/workflows/update.yml/dispatches`
   Method: POST. Body: `{"ref":"main"}`
   Headers: `Authorization: Bearer YOUR_TOKEN`, `Accept: application/vnd.github+json`.
4. Keep the token private. Anyone with it can start your workflow.

## Alerts and price history

- **RSS feed.** The site publishes `feed.xml` with new deals, big discounts and fresh price
  drops. Add `https://YOUR-USERNAME.github.io/heyyoupgrade/feed.xml` to any RSS reader.
- **Browser notifications.** The "Notify me of new drops" button at the bottom of the page
  asks your browser for permission. These only arrive while the page is open in a tab.
- **Price history.** The fetcher saves a deal's price whenever it changes, and every few days if
  it stays the same, for up to 90 days. Every card has a **Price history** drop-down with a
  chart of the lowest and highest price seen. History only starts from when the site first saw
  a deal, so the 3-month view fills in over time. After about three days, deals can also show
  "30-day low" or "% under 30-day avg".
- **Basket box.** The box on the right of every page lists what you have pinned, with a total.
  On narrower screens it opens from the Basket button in the corner.

## Getting more retailers (Currys, Overclockers and small UK shops)

**Why some tabs are thin.** The site can only read what a shop lets automated visitors read.
GitHub's servers are refused by some shops (CCL answers HTTP 403 to them), and the lists for
those shops are then the last copy that was saved. The page marks them "Price checked 5d ago".
Pretending to be a normal browser to get past that is not something this site does.

**Best route for big shops: affiliate product feeds.** Currys and Overclockers both run
affiliate programmes (check Awin first, then Impact, CJ and Partnerize). A feed is the
retailer's own catalogue file, so it is allowed, complete and has images. Apply, wait for
approval, create a CSV feed, and put its URL in the `AWIN_FEED_1` secret. To let a feed fill
the part tabs too, add `"parts": true` to that source in `sources.json`.

**Best route for small shops: Shopify.** Many small UK PC shops run on Shopify, which publishes
each collection as JSON at `https://SHOP/collections/NAME/products.json`. Test one by opening
that address in your browser. If you see product data, add the shop to `sources.json`:

```json
{
  "name": "Small shops",
  "type": "shopify_json",
  "enabled": true,
  "top": 10,
  "shops": [
    {
      "retailer": "Shop name",
      "base": "https://www.example-shop.co.uk",
      "collections": [
        { "handle": "graphics-cards", "cat": "gpu", "rank_by": "Shop order" },
        { "handle": "gaming-pcs", "cat": "deals" }
      ]
    }
  ]
}
```

`cat` is one of gpu, cpu, memory, motherboard, psu, case, cooling, or `deals` for complete PCs
and bundles. After a run, **Where prices come from** shows whether each shop answered.

**Other routes.** Email a shop and ask for a product feed or partner access. Many small
shops say yes. Price comparison networks (Kelkoo, Idealo) also offer partner data.

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
- **HotUKDeals.** The site uses the documented Pepper Public API (the platform behind HotUKDeals)
  to pull the hottest deals for each section. Its docs do not say how access, rate limits or
  commercial use work, so check **Where prices come from** after the first run. If it shows
  "Failing" with HTTP 401 or 403, the API needs credentials, and you would need to ask Pepper
  for access. Read their terms before you earn money from the site.
- **Accuracy.** Specs are read from post titles by pattern matching, so a few will be
  wrong or blank. The page always links to the original post or retailer page so
  people can check before they buy.
- **Affiliate links.** In the UK you must make it clear when links earn you commission.
  Add a short line to the footer when you start using them.

## Visitor counter and click counts (GoatCounter, free)
1. Go to goatcounter.com, choose "Sign up", and pick a site code (for example `heyyoupgrade`). Your stats live at `heyyoupgrade.goatcounter.com`.
2. In GoatCounter go to Settings, tick "Allow adding visitor counts on your website", and save.
3. In `index.html` find `var GC_CODE = "";` and put your code between the quotes, then upload `index.html`.
4. The footer then shows "N page views so far" and each "View at ..." click is counted per shop. The figure is cached for a few hours, so it is not a live "online now" number. Check GoatCounter's terms for your plan (the free plan may be for non-commercial use only).

## Getting shops onto the site
- The "For retailers" page explains the feed format. Shops open a public GitHub request with their feed address.
- To add one: open `sources.json`, find "Retailer feeds", add `{"retailer": "Shop name", "url": "https://shop.co.uk/feed.csv"}` inside `shops`, and set `"enabled": true`. Only links on the shop's own website are accepted, and each shop is capped at 30 products per category.
- eBay UK (optional, untested): create a free account at developer.ebay.com, copy the Client ID and Client Secret into repo secrets `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`, then set the "eBay UK" source to `"enabled": true`.
