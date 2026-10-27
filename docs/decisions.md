# Decisions

Things I had to decide while building this, and why. Newest at the bottom.

## Table extracts instead of an RFC connection

Reading from SAP directly (RFC, OData) would need a system, a user and authorizations. Most data migration projects start with exports anyway, because the consultant gets them long before anyone grants system access. CSV per table, original field names, nothing else.

## Separate brownfield and greenfield

My first rule list mixed the two. CVI links (KNA1-LIFNR, LFA1-KUNNR), number range collisions and form of address mapping only matter in a system conversion, where ECC records turn into BPs before the conversion. In a new implementation you load BPs fresh and the old links are irrelevant. The staging file is the opposite: it only makes sense for greenfield. Every rule now carries the path it belongs to and `--path` filters them.

## IBAN lives in TIBAN

I first modeled the IBAN as a column of LFBK. It is not. LFBK and KNBK hold bank country, bank key and account number, TIBAN holds the IBAN under that key. That is also why the BLZ/account versus IBAN check exists at all: there are two places for the same information, and they drift apart.

## SQL for set-based rules

Last activity, broken links, number collisions and the readiness score are joins and aggregates. Writing them in pandas works, but SQL is easier to read for anyone who knows SAP tables, and it is the language a reviewer at a client would check. The extracts go into an in-memory SQLite database, the queries live in `sql/`.

## Archive candidates never have open items

A customer with no posting since 2019 but one open invoice is not dead, somebody owes money. `inactive_partners.sql` excludes everything with open items, whatever the age. The tests check that no partner with open items is ever suggested.

Activity is taken across all company codes. A customer that is quiet in company code 1000 and active in 2000 is not an archive candidate. The generator plants ten of those to make sure.

## Duplicate score: weights and thresholds

Name 55 %, street 25 %, house number 10 %, city 10 %. Name dominates because companies move and the address changes, the name rarely does. These weights are judgment plus a few runs on the sample data, not a fitted model. I have no labeled real data to fit on.

Score 90 and above is an error ("likely duplicate"), 80 to 90 is a warning ("check"). I would rather send a few extra pairs to a human than merge two companies automatically. A wrong merge is much harder to undo than a skipped one.

## GmbH and KG at the same address

"Müller GmbH" and "Müller KG" at the same address get minus 15 and land at 85, in review. Not higher, because they are two legal entities. Not lower, because two companies of one family at one address are often related (one owns the building, one runs the business) and someone should look at them anyway.

## Same VAT ID, different city

First version: same VAT ID meant score 100. Then I added branches to the sample data, same company and VAT ID in another city. They all came out as duplicates. In real data some of those are ship-to accounts that exist on purpose. Now same VAT ID plus different city scores 85, review band. It still costs 5 false positives per sample, which I left visible in the results.

## Realistic address distribution

The first generator drew postal codes at random. Every customer had its own postal code, blocking produced 99 candidate pairs and everything looked great. Real customer lists cluster: a few hundred partners in the home town, a long tail elsewhere. With clustered towns the same data gives 43,000 candidate pairs, still fast, and the results got more honest.

## v0.1 to v0.2 after the first holdout run

First run with clustered addresses (seed 42), R01 recall 0.975, holdout recall 0.935. The misses:

- "Rust & Bruder Gesellschaft mbH" was not recognized as GmbH. Added the long form to the legal form patterns.
- A partner entered with the city district ("Bonn-Mitte") and a mistyped postal code. Postal code block and name/city block both missed it. Added a fourth block on street plus house number. It added 2 candidate pairs.

Since I had now looked at seed 42, it no longer counts as a test. I generated seeds 7 and 2024 and ran them once. Results in the README. One holdout pair is still missed: a typo that runs into the legal form ("SchaafU G"). I kept it as a known miss instead of writing a rule for that one case.

## Exact checks score 100 %, and that means little

R02 to R13 find every planted error on every seed. They are deterministic checks against the exact errors I planted, so that number only shows the checks are wired up correctly. The real test would be a client extract.

## Not migrated is its own file

Leaving records behind is a business decision, not a technical one. `not_migrated.csv` lists every left-out record with the reason, so the sales and purchasing departments can object before cutover, not after.

## A generic profiler as a second opinion

I ran a general purpose data profiler over the customer extract to see what a tool without SAP knowledge would say. It gave a quality score of 82 out of 100 and its loudest warning was NAME2 being 99 % empty. In SAP that is normal, NAME2 is the second name line and most firms do not need it. It also read the postal code column as a number, which drops leading zeros.

Two points from that run were right and missing here:

- duplicate primary keys in the extract. Added R00, which runs before everything else.
- placeholder values. "xxx", "-" or "unbekannt" in a mandatory field look filled to a simple empty check. R02 now treats them as empty.

The leading zero problem went into the data model notes, because it happens when someone opens the CSV in Excel, not inside this tool.

## The worklist moves into a web app

Excel is the format the business knows, so the Excel export stays. But with three departments editing their own copies, nobody knows the current state. The web app keeps one list in SQLite with status, owner and comment per finding, and a history table that records who changed what. The Excel export now carries those statuses, so Excel becomes a snapshot instead of the master.

## Readiness then and now

The score as found never changes, it describes the extract. The score now ignores findings marked fixed or false positive. Showing both makes progress visible without rewriting history. Same formula as the CLI, as a SQL view in `sql/run_readiness.sql`.

## A false positive needs a reason

Marking something as a false positive makes it disappear from the score. Without a reason that is an easy way to make numbers look good. The API refuses a false positive without a comment, single and bulk.

## Bulk updates are all or nothing

If one id in a bulk update does not exist, nothing changes. Half-applied bulk changes are hard to explain in a status meeting.

## No Google Fonts

The design uses Fira Sans. Loading it from Google's servers sends the visitor's IP address to Google, and German courts have fined websites for exactly that (LG München, 2022). The page uses the font if it is installed and falls back to the system font. Nothing is loaded from outside.

## API linter and scorecard

I ran an OpenAPI linter and a design scorecard over the generated spec. The linter went from 93.9 to 98.9 after renaming path parameters to camelCase, documenting error responses and adding descriptions. The scorecard still gives a low grade. It expects OAuth on every endpoint, rate limiting, caching headers and batch operations. I added the batch update because the dashboard needed it and a cache header on the rule list. The rest makes sense for a public API with thousands of clients, not for a tool a project team runs on one laptop. That is a choice, written down here so it does not look like an oversight.

## Zip uploads

An uploaded zip is untrusted. The app only takes files ending in .csv, uses the base name and ignores every folder inside the archive. A file called `../../x.csv` ends up as `x.csv` in the run folder. A test uploads exactly that. Uploads above 50 MB are refused.
