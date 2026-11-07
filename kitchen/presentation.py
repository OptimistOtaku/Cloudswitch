import csv
import json


def money(paise):
    return f"INR {paise / 100:,.2f}"


def render(response):
    kind = response["kind"]
    if kind == "clarify":
        return response["question"]
    if kind == "closed":
        return (
            "Shift closing recorded.\n```json\n"
            + json.dumps(response["report"], indent=2)
            + "\n```"
        )
    plan = response["plan"]
    economics = plan["economics"]
    lines = [
        f"### Cloudswitch · {'Approved version ' + str(plan['version']) if kind == 'approved' else 'Proposal ' + response['proposal_id']}",
        f"Expected contribution **{money(economics['expected_contribution'])}** after ingredients, packaging, fees, discounts and market trips.",
        f"Purchase surplus at risk: {money(economics['purchase_surplus_cost_at_risk'])}. Batch leftovers: {sum(r['expected_leftover_portions'] for r in plan['prep'])} portions.",
    ]
    if plan["baseline_blockers"]:
        lines += ["\n**What changed from the full menu**"] + [
            "- " + s for s in plan["baseline_blockers"]
        ]
    if plan["confirmed_at_risk"]:
        lines += [
            "\n**Confirmed orders at risk — owner action needed:** "
            + json.dumps(plan["confirmed_at_risk"])
        ]
    lines += ["\n**Buyer**"] + [
        f"- {r['market_name']}: {r['grams']} g {r['ingredient']} · {money(r['cost'])} · arrive {r['arrival']}, buy before {r['buy_before']} (closes {r['closes']})"
        for r in plan["buying"]
    ]
    lines += ["\n**Cooks**"] + [
        f"- {r['cook']}: {r['dish']} · {r['portions']} portions · {r['start']}–{r['finish']}"
        for r in plan["prep"]
    ]
    lines += ["\n**Menu operator**"] + [
        f"- {r['brand']} / {r['dish']}: {'offer ' + str(r['portions']) + ' portions' if r['available'] else 'pause'}"
        for r in plan["menu"]
    ]
    if plan["questions"]:
        lines += ["\n**Needs confirmation**"] + ["- " + q for q in plan["questions"]]
    lines += [
        "\nForecast evidence: "
        + str(next(iter(plan["menu"]))["forecast"]["comparable_days"])
        + " comparable service days. Quotes and use-by dates supplied by the kitchen."
    ]
    lines += [
        "Projected contribution excludes rent, salaries, utilities and tax. Delivery-app availability needs operator action."
    ]
    if kind == "proposal":
        for index, alternative in enumerate(plan["alternatives"], 1):
            offered = ", ".join(
                f"{dish} × {quantity}"
                for dish, quantity in alternative["portions"].items()
                if quantity
            )
            lines.append(
                f"Alternative {index}: {offered or 'pause all dishes'} · expected contribution {money(alternative['economics']['expected_contribution'])} · confirmed at risk {sum(alternative['confirmed_at_risk'].values())}. Approve with `approve {response['proposal_id']} option {index}`."
            )
        lines += [
            f"Owner: reply `approve {response['proposal_id']}` in this thread to update all three lists."
        ]
    return "\n".join(lines)


def export(folder, response):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plan.json").write_text(json.dumps(response, indent=2), encoding="utf-8")
    (folder / "brief.md").write_text(render(response), encoding="utf-8")
    for name, rows in (
        ("buying", response["plan"]["buying"]),
        ("prep", response["plan"]["prep"]),
        ("menu", response["plan"]["menu"]),
    ):
        with (folder / (name + ".csv")).open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            fields = list(rows[0]) if rows else ["empty"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
