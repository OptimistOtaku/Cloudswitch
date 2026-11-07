# Cloudswitch

A buyer reports a stockout in the team room. Cloudswitch checks which dishes
it affects, whether another market is reachable, what the trip costs, and what
the available cooks can prepare. The owner approves a version that updates the
buying list, prep tasks and internal menu together.

Built for the Flip the Switch **Best Business Workflow** track. The supplied
Swiggy/Zomato-style exports, brands, markets, prices and shifts are synthetic.

[Watch the demo](demo/kitchen-shift-animated.mp4). The 78-second video combines
accelerated screen recordings of the actual Mattermost conversation and approved
operating plan with an illustrated kitchen, moving characters, pop-up chat bubbles,
naturally paced Indian narration and sound design. The opening uses fast illustrated
cuts, and the final frame credits Switch with its official mark. Neha Mehta owns the shift, Ravi Sharma buys ingredients,
and Asha Rao cooks. The workflow uses sample kitchen data. The corresponding
[verified run](demo/verified-run.json) records the room, thread and output
totals. [Captions are included](demo/kitchen-shift-animated.srt). The local demo
page provides an interactive view of the same workflow.

The Switch mark comes from the [official Switch repository](https://github.com/sandbox-quantum/switch/blob/main/gateway/public/switch_logo_light.svg).

## Run a kitchen shift

Python 3.11+ is sufficient. The planner, storage, tests and web interface use
the standard library. Run these commands from this directory.

```sh
python -m kitchen.cli --data my-shift init
python -m kitchen.cli --data my-shift plan
python -m kitchen.cli --data my-shift web
```

Open http://127.0.0.1:8787. Build the plan and report a market update. Natural
language messages require an authenticated `codex` CLI on PATH. Alternatively
set `KITCHEN_MODEL_BACKEND=openai`, `OPENAI_MODEL`, `OPENAI_API_KEY` and optionally
`OPENAI_BASE_URL` for a compatible Chat Completions endpoint. There is no canned
AI fallback. The page reports inference failures. Only its local rehearsal
uses the demo identity selector. Real Switch approvals check the sender ID.

An example of the complete drill is below. Use the same room thread for all
updates and approvals.

1. Ask for the dinner plan. The Chinese cook is on leave. Four Indian dishes
   remain feasible, with expected contribution **INR 2,375.40**.
2. Report “Main market is out of green chillies. I can reach East Market at
   4:30 pm.” The agent asks the buyer to confirm stock there. It proposes a
   feasible menu without relying on unknown supplier availability.
3. Report “East Market confirmed fresh green chillies are in stock.” The
   emergency van trip costs INR 1,800 in this synthetic scenario. Forecast
   demand alone does not justify it.
4. Report “We have 18 confirmed paneer bowl orders in total for dinner.” The
   planner now prioritizes fulfillment of these orders and recommends the trip.
5. Reply `approve <proposal-id>` as the configured owner. One approved version
   contains all three lists and the shared-stock reservation. Ask in another
   thread, use an old proposal, or approve as the buyer to see rejection.
6. Change East Market closing to 4 pm and request a new plan. The late trip
   becomes infeasible and the confirmed orders are explicitly flagged.

The emergency trip cost is an editable scenario assumption. Use supplier
quotes, transport costs and prep times from a real kitchen before comparing
operating decisions.

## Connect the actual team room through Switch

1. Start [Switch Console](https://docs.switchagents.ai), its local server and
   Mattermost. Create a dedicated kitchen room and an external agent named
   `kitchen-shift`. Add it to that room with an integration profile supporting
   incoming messages. Allow the kitchen team to address it.
2. Copy the values in `.env.example` into your shell environment. This project
   intentionally does not load any surrounding repository credentials. Obtain
   exact opaque participant IDs using the agent's `connect_to_room` / room
   context operation. Put the owner's ID in `KITCHEN_OWNER_ID` and permitted
   buyer/cook IDs in `KITCHEN_TEAM_IDS`. Do not use display names as IDs.
3. Use a **separate data directory** for the live room. Then run:

```sh
python -m kitchen.cli --data live-shift init
python -m kitchen.cli --data live-shift switch
```

The process receives Switch SSE messages, maintains the connection heartbeat,
stores human messages in a durable inbox, calls the model, and posts a threaded
proposal via Switch's `post_message` operation. Owner approval is parsed by code
and checked against the configured owner, proposal revision, room and thread.
The model cannot approve a plan. Model calls contain kitchen data and the
human message, never the Switch credential.

The legacy SSE transport is supported by the inspected Switch protocol. A
server buffer gap is reported in the worker log and requires resending any
unacknowledged update. Replies are at least once after an ambiguous network
failure. Inbox and planning actions are idempotent by message ID.

## Data and calculations

Edit `kitchen.json` **before the first run**, or use chat for supported facts
after initialization. SQLite becomes the source of truth after initialization.
`snapshot` shows the current facts, versions and closing records. Create a new
data directory to start an independent scenario.

`orders.csv` contains order ID, platform, dish, ISO timestamp with timezone,
delivery zone, quantity, revenue, discount, fees and service. Money is integer
INR paise, quantities integer grams. The importer rejects duplicate order lines.
It averages each dish across prior matching weekdays and services, including
zero-sale dishes on represented dates, and exposes those dates. A date with no
rows at all cannot be distinguished from a missing export. Prices, discounts
and platform fees used for the upcoming plan are configured in the dish table.
CSV settlement amounts and delivery zones are retained for inspection. The
prototype does not estimate zone-specific demand or live platform fees.

The planner enumerates menu subsets and compares feasible plans. For each
dish, target sales are the greater of forecast and total confirmed orders.
Preparation rounds up to recipe batch size. It checks cook skills, serial
workload, shift times, supplier availability, market arrival/closing times,
travel time and stock use-by dates. Shared ingredients aggregate before buying.
Existing stock is charged at its recorded cost, purchases at full pack cost,
and trips once per market. Confirmed-order shortfall ranks before contribution.
An infeasible order remains visible to the owner.

Contribution is revenue after kitchen-funded discounts, platform fees,
packaging, ingredients and market trips. Rent, salaries, utilities, taxes,
cancellation penalties and refunds are outside that calculation. Purchase
surplus cost measures unallocated purchased stock at risk. Batch leftovers
measure portions prepared above expected demand. Both are projections.

This bounded planner compares whole-menu subsets. It uses a deterministic cook
assignment and supplier selection, assumes prep before service and supports
same-day market hours. It does not solve a globally optimal route, vary dish
targets continuously, infer shelf life, or invent recipe substitutions.

## Approval, exports and actual closing

Run `plan`, `action` or `event` to export `artifacts/brief.md`, `plan.json`,
`buying.csv`, `prep.csv` and `menu.csv`. The page also writes these exports.
The internal menu sheet requires an operator to apply delivery-app changes.
Run `snapshot` for the authoritative approved version. Proposed exports are
labeled as proposals. One SQLite transaction saves each approved set of lists.

Record closing with `close <JSON>` as owner, listing every prepared dish:

```text
close {"paneer-bowl":{"sold":5,"carried":0,"discarded":1},"veg-bowl":{"sold":6,"carried":0,"discarded":0},"paneer-wrap":{"sold":6,"carried":0,"discarded":0},"veg-wrap":{"sold":5,"carried":1,"discarded":0}}
```

Each dish must balance to its prepared portions. Closing is stored once per
approved version, separate from projected contribution. Actual financial
margin requires settlement and purchase receipts. Raw inventory counts for
the next shift must be supplied by the kitchen. Carried food needs the
kitchen's own food-safety checks. A reservation alone earns no waste-saving
claim.

## Verify

```sh
python -m unittest discover -s tests -v
python demo/replay.py
```

Tests cover cook absence, shared stock, known financial totals, unknown supplier
stock, market closure, changed decisions after a confirmed order, expired stock,
concurrent/repeated approval, rejected owner/thread/revision mismatches,
transaction rollback and closing conservation. The inspected protocol source
is [Switch's agent protocol](https://github.com/sandbox-quantum/switch/blob/main/docs/official/internals/agent-protocol.md).

The kitchen workflow uses standard Switch messaging and is independent of
scheduler PR #1573. The project runs locally. A final submission needs its
participant's review of the setup and claims, public repo and video links,
and manual entry through the hackathon submission form.
