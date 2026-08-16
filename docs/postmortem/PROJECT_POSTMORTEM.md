# Next Candle Bot: Problems Faced & How They Were Solved

A postmortem of every integration, code, and methodology issue hit while building the Deriv synthetic-indices trading bot, in the order they surfaced — plus generalized checklists at the end for the two recurring problem classes (broker/API integration, and validating a trading strategy) since those will show up again on future projects.

---

## Part 1: Deriv API Integration

### 1. Leaked credential in plain chat

**Symptom:** none directly — a security exposure, not a functional bug. **What happened:** an API token got pasted directly into a chat message as plain text (via an IDE file-change diff), twice across the conversation, once for each of two different tokens. **Fix:** treated each occurrence as burned — never repeated the token back in any tool call or message, and flagged clearly that it was now part of the conversation's context. **Lesson:** credentials belong in `.env` files and shell environment variables only. If a token is ever visible in a chat transcript, IDE diff, or screenshot, treat it as exposed regardless of intent — don't wait for evidence of misuse before being careful with it.

### 2. `[InvalidToken] The token is invalid` — wrong generation of the API entirely

**Symptom:** every WebSocket `authorize` call was rejected with an explicit invalid-token error, across two different freshly-generated tokens. **Root cause:** Deriv has (as of mid-2026) two parallel API generations running simultaneously:
- **Legacy:** connect directly to `wss://ws.derivws.com/websockets/v3?app_id=<numeric_id>`, then send `{"authorize": "<token>"}` as an in-band message on that same connection.
- **New ("Options API"):** call a REST endpoint with the token as an `Authorization: Bearer` header to get a short-lived, single-use OTP, then connect to a WebSocket URL that already has the OTP embedded — no in-band authorize message at all.

The new-format token (`pat_...`, ~68 characters) was completely valid — it just belonged to the new generation and could never work sent through the legacy in-band flow. **Fix:** rewrote the connection layer to do the REST → OTP → WebSocket handshake (details below). **Lesson:** an "invalid token" error does not always mean the credential value is wrong. It very often means the *authentication method* being used doesn't match what the API currently expects — check for a platform migration before assuming the credential itself is bad, especially for any API that's touched a "new dashboard" or "new developer portal" recently.

### 3. New-portal app_id used against the legacy WebSocket host → `HTTP 401` at handshake

**Symptom:** using the new alphanumeric app_id (from the new portal's "Registered Apps" page, e.g. `34063V8kXkiukAuWNoQEV`) as the `?app_id=` query param on the legacy `ws.derivws.com` host caused the WebSocket handshake itself to fail with HTTP 401 — worse than before, since previously at least the connection succeeded and only `authorize` failed. **Root cause:** the new-generation app_id is not a drop-in replacement for the legacy numeric one; it belongs to an entirely different host and REST-first flow. **Fix:** reverted to the legacy numeric app_id (`1089`, Deriv's shared public test ID) as a temporary known-good state while researching the real fix, rather than guessing further. **Lesson:** when a new value produces a *different, more severe* error than the old one, that's a signal you're mixing two incompatible systems, not that you're close to a fix — step back and re-verify the whole flow rather than keep swapping one field at a time.

### 4. Discovering the real flow: REST OTP → WebSocket

**Symptom:** needed the actual, current request/response shapes for the new API generation — legacy docs and AI-search-summarized doc pages gave inconsistent or unverifiable answers. **Root cause:** the new Options API's authentication docs are behind a JavaScript-rendered SPA that automated fetch tools can't render (they only see the page title). **Fix:** found and used `github.com/deriv-com/deriv-api-schemas` — a real, auto-published, versioned JSON Schema repository — as ground truth instead of scraped docs. This confirmed the exact flow: `POST /trading/v1/options/accounts` → `POST /trading/v1/options/accounts/{accountId}/otp` → connect directly to the returned WebSocket URL. Host: `api.derivws.com`, required headers `Deriv-App-ID` and `Authorization: Bearer <token>`. **Lesson:** when official docs are a JS SPA your tools can't read, look for the provider's raw schema/spec repo on GitHub (OpenAPI JSON, JSON Schema bundles) — it's usually more authoritative than a doc site anyway, and it's plain-text fetchable.

### 5. `401 Invalid application` despite a real app_id and a real token

**Symptom:** sending both `Deriv-App-ID` and `Authorization: Bearer` headers together (individually, each was validated as present via distinct error messages — "Missing authorization header" and "Deriv-App-ID header is required for PAT tokens") still got rejected once both were present, with a generic "Invalid application" error — even though the app_id was confirmed to exist and the token was confirmed active. **Root cause (two parts, found in sequence):**
- The `POST /accounts` call needs a body with an **undocumented required field**: `{"currency": "USD", "group": "row", "account_type": "demo"}`. The `"group": "row"` field appeared nowhere in any fetched documentation or schema example — it was only discoverable by having previously hit this exact error on a prior project and recording the fix.
- Even with the correct body, the token needed **both "Trade" and "Account management" scopes** checked at creation time — a token with only "Trade" scope got a different, more specific error (`403 Insufficient scopes`) once the app_id/body issue was fixed, which then pointed at the real remaining gap.

**Fix:** applied both fixes together — correct request body, broader token scope — which finally returned `200 OK` with a real demo account (`account_id`, balance, currency). **Lesson:** a generic "invalid" error from a REST endpoint often means the request *shape* is subtly wrong (missing an undocumented field), not that the credentials are bad. When you get a more specific error after a partial fix (e.g. "insufficient scopes" instead of "invalid application"), that's progress — treat it as narrowing down, not as a new unrelated problem.

### 6. Field-name differences from the legacy API

**Symptom:** several requests that would have worked against the legacy API were rejected with `Properties not allowed: <field>` errors under the new generation. **Specific cases found:**
- `proposal`/`buy` requests: the symbol field is `underlying_symbol`, not `symbol`.
- `contracts_for` requests: does not accept a `currency` field at all (legacy docs suggested it did).

**Fix:** corrected each field name/shape empirically, one real API call at a time, rather than assuming legacy conventions carried over. **Lesson:** don't assume a "new API generation" only changed the auth/transport layer — message *field names* can silently change too. Test each request type against the real API individually before building a whole module around assumed field names.

### 7. Two different field names for the same concept: `epoch` vs `open_time`

**Symptom:** code written to read `open_time` from candle data worked for live streamed updates but would have thrown a `KeyError` on historical/backfill responses. **Root cause:** live `ohlc` push messages carry both `epoch` (the tick time of that specific update — changes every tick) and `open_time` (the fixed candle-open identifier — stable until a new candle starts). Historical/snapshot `candles` list entries only ever carry `epoch`, which *is* the open time for those entries — there is no separate `open_time` field on them. **Fix:** used a fallback lookup (`raw.get("open_time", raw.get("epoch"))`) so the same parsing function handles both shapes correctly, and wrote dedicated tests for each shape rather than assuming one representative fixture covered both. **Lesson:** when an API has both a "snapshot" and a "live push" variant of similar data, verify their field shapes independently — don't assume the live-stream shape is a superset or subset of the snapshot shape.

### 8. Deriv silently caps `ticks_history` at 1000 candles per request

**Symptom:** requesting `count: 2000` (or 5000) candles silently returned only 1000, with no error — this was only noticed because a backtest's logged "fetched N candles" count didn't match what was requested. **Root cause:** an undocumented (or at least non-obvious) per-request cap on historical candle count. **Fix:** built pagination using the `end` parameter: after fetching a page, request the next page with `end = oldest_candle.open_time - granularity_seconds`. Verified the exact boundary math empirically before trusting it (fetched two adjacent pages and confirmed the gap between them was exactly one candle-width — no overlap, no missing candle) rather than assuming the `end` parameter's inclusive/exclusive semantics. **Lesson:** APIs that cap page/result size don't always error when you ask for more — they may just silently truncate. Always log and check the *actual* returned count against the requested count, especially right after building something new on top of an API response.

---

## Part 2: Code Bugs Caught During Development

### 9. `pydantic-settings` silently breaks plain comma-separated `.env` values

**Symptom:** `SYMBOLS=R_10,R_25,R_50` in `.env`, loaded into a `list[str]`-typed settings field, raised a JSON decode error at startup. **Root cause:** `pydantic-settings` tries to JSON-decode any complex-typed (e.g. `list[str]`) environment variable before validators run, so plain comma-separated strings (not `["R_10","R_25"]` JSON syntax) fail immediately. **Fix:** kept the field as a plain `str` in the settings model and exposed a computed `symbol_list` property that splits on commas, instead of fighting the library's built-in JSON-decoding behavior. **Lesson:** don't type env-var-backed settings fields as `list`/`dict` if you want simple `.env` syntax — keep them as `str` and parse on access.

### 10. `datetime.datetime.utcnow()` deprecation warnings

**Symptom:** test runs showed `DeprecationWarning: datetime.datetime.utcnow() is deprecated`. **Fix:** replaced with `datetime.now(datetime.timezone.utc)` everywhere a default timestamp was generated (ORM model defaults, repository functions). **Lesson:** cheap to fix immediately when noticed; not worth leaving for "later" since it compounds across every file that copies the same pattern.

### 11. A test that passed for the wrong reason (vacuous assertion)

**Symptom:** a "boundary exclusion" test for the swing-detection algorithm passed, but on inspection the fixture produced an *empty* result set — so an assertion like `all(x not in boundary for x in results)` was trivially true regardless of whether the boundary logic actually worked. **Fix:** rebuilt the fixture so it produced real, non-boundary results *and* had extreme values at the boundary positions, so the assertion was actually exercising the logic it claimed to test. **Lesson:** when a test's assertion is a universal quantifier over a collection (`all(...)`, `any(...) is False`), double-check the collection isn't empty — an empty collection makes almost any such assertion pass for free.

### 12. Hand-built test fixture had wrong arithmetic (caught before running)

**Symptom:** none — caught by manually recomputing the expected values before trusting the test. **Root cause:** an ATR (Average True Range) test fixture used candles with *drifting* closes, which pulled the "gap" term of the true-range formula above the intended constant value (true range came out to 3, not the assumed 2). **Fix:** redesigned the fixture with *flat* (non-drifting, identical) candles, verified by hand-computing the true range for a couple of candles before writing the assertion. **Lesson:** for any fixture involving a multi-term formula (like true range's `max(high-low, |high-prevclose|, |low-prevclose|)`), compute the expected value by hand or in a scratch script *before* writing the test assertion — don't assume a "looks reasonable" fixture produces the constant you intended.

### 13. Untracked `open` value flipped a test candle's color

**Symptom:** a test asserting a "one-color streak" signal fired instead got a different signal ("fvg"), because the candle intended to be bullish was actually bearish. **Root cause:** the fixture explicitly set `high`/`low`/`close` but the `open` value (which determines bullish vs. bearish) was set inconsistently with the intent, and nothing cross-checked it. **Fix:** verified the exact expected behavior via a small interactive script before finalizing the fixture, and once the bug was found, fixed the specific `open` value. **Lesson:** when a candle's classification (bullish/bearish/doji) matters to a test, explicitly compute and comment the expected classification next to the fixture — don't rely on "close > 0" intuition without checking `open` too.

### 14. Passing `client=None` crashed a background task, not the test itself

**Symptom:** a test passed, but its logs showed an `AttributeError: 'NoneType' object has no attribute 'subscribe'` from a background `asyncio.create_task` that ran after the awaited call returned. **Root cause:** the code under test spawns a background contract-monitoring task using the same client object; passing `None` for "we don't need this in this test" broke that background task silently (in the sense that it didn't fail the `await` the test was checking, just logged an error asynchronously). **Fix:** supplied a minimal fake client with a working `subscribe()` method instead of `None`. **Lesson:** when a function under test spawns background tasks (`asyncio.create_task`), a "None is fine, I don't need it" assumption about a dependency can be wrong if that dependency is *also* used by the background path — check what *all* code paths from the function use, not just the synchronous one you're directly asserting on.

### 15. Design gap: business logic importing a global DB session directly

**Symptom:** none yet — caught by review before writing tests, not by a test failure. **Root cause:** the orchestrator was about to import and use `persistence.db.SessionLocal` (the real, production-configured session factory) directly inside its methods, which would make it impossible to test against an in-memory database without monkeypatching a global. **Fix:** changed the constructor to accept `session_factory` as an injected parameter (matching a pattern already used elsewhere in the codebase for the risk manager), defaulting to the real one only at the actual application entry point. **Lesson:** any class that talks to a database, external API, or other global singleton should receive that dependency through its constructor, not import the "real" global directly — decide this before writing the class, since retrofitting it after tests are written is more work.

### 16. Re-deriving a result from a proxy value instead of using the authoritative one

**Symptom:** none directly, but would have caused silent misclassification. **Root cause:** contract settlement logic inferred "won" vs. "lost" from the *sign* of the profit value, when the broker's API response already includes an explicit, authoritative `status` field (`"won"`/`"lost"`) for exactly this purpose. **Fix:** switched to trusting the API's own status label directly. **Lesson:** if an API response includes an explicit field for the exact classification you need, use it — don't re-derive the same classification from a different field "because it should be equivalent." It usually is, until it isn't (e.g. a breakeven edge case, a fee, a rounding difference), and there's no benefit to the re-derivation anyway.

### 17. Floating-point precision in a test assertion

**Symptom:** `assert entry_trade.expiry_price == -2.1` failed with `-2.0999999999999996 == -2.1`. **Root cause:** `13.9` (and other decimal literals) aren't exactly representable in binary floating point, so arithmetic on them can differ from the "obvious" decimal result by a tiny epsilon. **Fix:** used `pytest.approx(-2.1)` instead of an exact equality check. **Lesson:** any test asserting an exact float result of arithmetic on non-trivial decimal literals should use an approximate-equality helper by default, not exact `==` — don't wait for it to fail.

---

## Part 3: Strategy/Backtesting Methodology Issues

These weren't code bugs — the code did exactly what it was told — but they're the same class of mistake: trusting a result before it had earned that trust.

### 18. Small sample size gave a misleading result

**Symptom:** a backtest on 1000 candles (Deriv's per-request cap, before pagination was built) showed one symbol at a 38.2% win rate — alarmingly bad. Re-running the same symbol with 5000 candles (via pagination) showed ~50%, a completely different picture. **Lesson:** an alarming (or exciting) result on a small sample is itself a signal to get more data before reacting to it, not a signal to act on directly. This cuts both ways — a *good*-looking small-sample result deserves exactly the same suspicion as a bad-looking one.

### 19. Parameter sweep found "best" configs that were pure overfitting

**Symptom:** systematically sweeping ~24 parameter combinations per symbol (96 total) found one config that scored 55.9% — clearly better than anything else tried. Out-of-sample validation (re-testing that exact config on data the sweep never saw) showed it collapse to 51.2%, barely different from the untuned default. **Root cause:** trying enough combinations against one dataset will always produce a "winner" by chance alone, even with no real underlying edge — the classic multiple-comparisons / data-snooping trap. **Fix/practice going forward:** never trust a "best of N tried configs" result without validating it against data that played no role in the search. **Lesson:** the more parameter combinations you try, the *more* (not less) out-of-sample validation you need before trusting the winner — a result chosen from a large search space needs more scrutiny than a single principled hypothesis test, not less.

### 20. A structural rule change succeeded where parameter tuning failed

**Symptom:** requiring a same-direction BOS (continuation) in addition to the existing CHoCH (reversal) gate — a single, principled change applied uniformly, not chosen from many candidates — noticeably stabilized results across all symbols (previously 38-59% swings, afterward a tight 50-52% band). **Lesson:** when tuning knobs on an existing rule doesn't help, consider whether the rule itself is structurally too permissive, rather than continuing to search the same parameter space harder. A tighter, more principled gate can fix instability that no amount of threshold-tuning will.

### 21. Even a principled change needs per-symbol out-of-sample validation

**Symptom:** after retiring a whole underperforming technique and keeping only the strategy's most promising piece (FVG mitigation + CHoCH + BOS), one symbol's in-sample result (R_25, 57.1%) still collapsed out-of-sample (47.6%), while another symbol's (R_50, 55.1%) held up closely (54.3%) on a fresh, non-overlapping dataset. **Lesson:** "we fixed the methodology" is not the same as "every result now generalizes." Validate per-instrument, every time, even after a structural improvement — a good methodology can still overfit to one specific symbol's historical quirks while genuinely capturing something real on another.

---

## Checklist A: Diagnosing "permission denied" / auth-style errors on *any* API

1. **Print the credential that's actually loaded** (masked — first/last few characters + length) right before it's used. A stale `.env`, wrong environment variable name, or unrefreshed process is a very common cause of "it looks right but isn't."
2. **Check for invisible corruption**: trailing whitespace, a stray newline, or surrounding quotes from a copy-paste can make a token *look* identical while failing every request. Strip whitespace defensively when loading any credential.
3. **Read the full error response body**, not just the status code or a generic message. Modern APIs usually return a specific reason (`invalid_token`, `insufficient_scope`, a named missing field) — that's the fastest path to the real cause, and a *different* specific error after a partial fix means progress, not a new problem.
4. **Confirm the authentication *method*, not just the value.** Common mismatches: a bearer token in a header vs. an API key as a query parameter; an in-band auth message on a persistent connection vs. a pre-auth REST call; an OAuth2 token vs. a separate personal-access-token system; a token scoped to one environment (sandbox/demo) vs. another (production/live).
5. **Check required headers beyond the credential itself** — an app ID, a client ID, a content-type, an API version header. A missing required header often produces a permission-flavored error even though the token is fine.
6. **Verify scope/permissions on the token, not just its validity.** A token can authenticate successfully but still get "permission denied" on a specific endpoint if it wasn't granted the right scope (e.g. read-only vs. trade/write, or account-management vs. trade).
7. **Write a minimal, isolated diagnostic script** that does nothing but authenticate and hit the simplest possible endpoint, printing the raw HTTP status and body. Don't debug auth through the full application — isolate it.
8. **Check the provider's changelog, dashboard, or schema repo for a platform migration.** If something that used to work stopped working with no code change on your side, assume the API itself may have changed before assuming your code broke. Prefer a raw schema/spec repo (OpenAPI JSON, JSON Schema bundles on GitHub) over a JS-rendered doc site your tools can't read.
9. **Fail fast and loud.** Don't let an auth failure retry silently or hide in a log file — surface the exact error where you'll actually see it, immediately, and treat auth/permission errors as non-retryable (retrying with the same bad credential wastes time and can look like hostile hammering to the server).

## Checklist B: Validating a trading strategy backtest before trusting it

1. **Get enough data before reacting to any result.** A single small sample can make a fine strategy look terrible or a mediocre one look great — re-run with substantially more data before drawing any conclusion, especially if the result is surprising in either direction.
2. **Never trust a "best of N tried configs" without out-of-sample validation.** The more combinations you swept, the more skeptical to be of the winner — hold back a genuinely untouched slice of history (not just "the latest data," since time passing doesn't guarantee no overlap with what was already tested) and re-score the winner there.
3. **Compare against the real breakeven line, not 50%.** Any instrument with an asymmetric payout (a typical binary/derivative contract, spread, commission) has a breakeven win rate above 50% — compute it from the actual payout ratio before judging whether a win rate is "good."
4. **When a rule is unstable, consider tightening the rule before tuning its thresholds.** If varying a parameter's numeric value doesn't produce consistent improvement, the rule itself may be structurally too permissive (e.g., accepting the very first weak signal of a pattern instead of waiting for confirmation).
5. **Validate per-instrument/per-symbol, every time — even after a structural fix.** A methodology that measurably improves stability overall can still fail on a specific instrument; don't generalize a portfolio-level improvement to every individual case without checking each one.
6. **Score against what actually determines payout**, not a proxy. For a direction-only contract, score "was price on the right side of entry at expiry," not "did price touch some intermediate target level" — the two can disagree, and only one of them is what you actually get paid on.
7. **Log actual returned data sizes, not just requested ones**, especially in a loop that runs many times (a sweep, a multi-symbol backtest) — a silent truncation (see Checklist A's API-cap issues) can quietly shrink your sample size without any error.
