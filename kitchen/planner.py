"""Deterministic planning. Integer grams, integer paise, explicit feasibility."""

from collections import defaultdict
from datetime import datetime, date
from itertools import product
from math import ceil
import csv


def minute(value):
    return (
        datetime.strptime(value, "%H:%M").hour * 60
        + datetime.strptime(value, "%H:%M").minute
    )


def clock(value):
    return f"{value // 60:02d}:{value % 60:02d}"


def forecasts(path, config):
    """Average whole comparable service days, including zero-sale dishes."""
    target = date.fromisoformat(config["date"])
    days = defaultdict(lambda: defaultdict(int))
    seen = set()
    with open(path, newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            identity = (row["platform"], row["order_id"], row["dish"])
            if identity in seen:
                raise ValueError("Duplicate order line " + str(identity))
            seen.add(identity)
            stamp = datetime.fromisoformat(row["ordered_at"])
            quantity = int(row["quantity"])
            if quantity < 0 or row["dish"] not in config["dishes"]:
                raise ValueError("Invalid order quantity or dish")
            if (
                stamp.date() < target
                and stamp.weekday() == target.weekday()
                and row["service"] == config["service"]
            ):
                days[stamp.date()][row["dish"]] += quantity
    return {
        dish: {
            "quantity": ceil(sum(day[dish] for day in days.values()) / len(days))
            if days
            else 0,
            "comparable_days": len(days),
            "dates": sorted(str(day) for day in days),
        }
        for dish in config["dishes"]
    }


def validate(config):
    date.fromisoformat(config["date"])
    for key in ("as_of", "service_start", "service_end"):
        minute(config[key])
    if minute(config["service_start"]) >= minute(config["service_end"]):
        raise ValueError("Service must start before it ends on the same day")
    for ingredient in config["ingredients"].values():
        for key in ("stock", "stock_cost_per_g", "pack_g"):
            if type(ingredient[key]) is not int or ingredient[key] < (
                1 if key == "pack_g" else 0
            ):
                raise ValueError("Invalid ingredient quantity/cost")
        date.fromisoformat(ingredient["use_by"])
        for quote in ingredient["quotes"].values():
            if (
                type(quote["price_per_g"]) is not int
                or quote["price_per_g"] < 0
                or quote["available"] not in (True, False, None)
            ):
                raise ValueError("Invalid supplier quote")
    for dish in config["dishes"].values():
        for field in (
            "price",
            "discount",
            "fee",
            "packaging",
            "confirmed",
            "batch_size",
            "batch_minutes",
        ):
            if type(dish[field]) is not int or dish[field] < (
                1 if field in ("batch_size", "batch_minutes") else 0
            ):
                raise ValueError("Invalid dish field " + field)
        if any(
            name not in config["ingredients"] or type(q) is not int or q <= 0
            for name, q in dish["recipe"].items()
        ):
            raise ValueError("Invalid recipe")
    for market in config["markets"].values():
        for key in ("opens", "closes", "arrival"):
            minute(market[key])
        if market["trip_cost"] < 0 or market["return_minutes"] < 0:
            raise ValueError("Invalid market costs/timing")
    for cook in config["cooks"].values():
        if minute(cook["start"]) >= minute(cook["end"]):
            raise ValueError("Invalid cook shift")


def calculate(config, demand, quantities):
    needs = defaultdict(int)
    prep = []
    menu = []
    blockers = []
    readiness = {
        name: max(minute(config["as_of"]), minute(c["start"]))
        for name, c in config["cooks"].items()
    }
    revenue = 0
    for name, dish in config["dishes"].items():
        quantity = quantities[name]
        menu.append(
            {
                "dish": name,
                "brand": dish["brand"],
                "portions": quantity,
                "confirmed": dish["confirmed"],
                "forecast": demand[name],
                "available": quantity > 0,
            }
        )
        if not quantity:
            continue
        batch_quantity = ceil(quantity / dish["batch_size"]) * dish["batch_size"]
        duration = ceil(quantity / dish["batch_size"]) * dish["batch_minutes"]
        cooks = [
            name
            for name, c in config["cooks"].items()
            if c["available"] and dish["skill"] in c["skills"]
        ]
        if not cooks:
            blockers.append(f"{name}: no available cook with {dish['skill']} skill")
            continue
        cook = min(cooks, key=lambda name: readiness[name])
        material_ready = minute(config["as_of"])
        for ingredient, grams in dish["recipe"].items():
            item = config["ingredients"][ingredient]
            if (
                item["stock"] >= grams * batch_quantity
                and item["use_by"] >= config["date"]
            ):
                continue
            arrivals = [
                minute(config["markets"][market]["arrival"])
                + config["markets"][market]["return_minutes"]
                for market, quote in item["quotes"].items()
                if quote["available"] is not False
                and max(
                    minute(config["as_of"]), minute(config["markets"][market]["opens"])
                )
                <= minute(config["markets"][market]["arrival"])
                < minute(config["markets"][market]["closes"])
            ]
            if arrivals:
                material_ready = max(material_ready, min(arrivals))
        start = max(readiness[cook], material_ready)
        end = start + duration
        if end > min(
            minute(config["service_start"]), minute(config["cooks"][cook]["end"])
        ):
            blockers.append(f"{name}: prep exceeds {cook}'s time before service")
        readiness[cook] = end
        prep.append(
            {
                "dish": name,
                "cook": cook,
                "start": clock(start),
                "finish": clock(end),
                "portions": batch_quantity,
                "expected_sales": quantity,
                "expected_leftover_portions": batch_quantity - quantity,
            }
        )
        for ingredient, grams in dish["recipe"].items():
            needs[ingredient] += grams * batch_quantity
        revenue += quantity * (
            dish["price"] - dish["discount"] - dish["fee"] - dish["packaging"]
        )
    purchases = []
    stock_allocations = {}
    used_markets = set()
    ingredient_cost = 0
    waste_cost = 0
    questions = []
    for name, grams in needs.items():
        item = config["ingredients"][name]
        usable = item["stock"] if item["use_by"] >= config["date"] else 0
        taken = min(grams, usable)
        stock_allocations[name] = taken
        ingredient_cost += taken * item["stock_cost_per_g"]
        remaining = grams - taken
        if remaining:
            choices = []
            for market, quote in item["quotes"].items():
                place = config["markets"][market]
                arrival = minute(place["arrival"])
                if arrival < max(
                    minute(place["opens"]), minute(config["as_of"])
                ) or arrival >= minute(place["closes"]):
                    continue
                if prep and arrival + place["return_minutes"] > min(
                    minute(row["start"])
                    for row in prep
                    if name in config["dishes"][row["dish"]]["recipe"]
                ):
                    continue
                if quote["available"] is None:
                    questions.append(
                        f"Buyer: confirm {name} stock at {place['name']} before relying on this supplier."
                    )
                if quote["available"] is True:
                    packs = ceil(remaining / item["pack_g"])
                    cost = packs * item["pack_g"] * quote["price_per_g"]
                    choices.append(
                        (
                            cost
                            + (0 if market in used_markets else place["trip_cost"]),
                            market,
                            cost,
                            packs,
                        )
                    )
            if not choices:
                blockers.append(f"{name}: no confirmed supplier reachable before prep")
                continue
            _, market, cost, packs = min(choices)
            place = config["markets"][market]
            used_markets.add(market)
            ingredient_cost += cost
            purchases.append(
                {
                    "ingredient": name,
                    "market": market,
                    "market_name": place["name"],
                    "grams": packs * item["pack_g"],
                    "required_grams": remaining,
                    "cost": cost,
                    "arrival": place["arrival"],
                    "closes": place["closes"],
                    "buy_before": min(
                        place["closes"],
                        clock(
                            min(
                                minute(row["start"])
                                for row in prep
                                if name in config["dishes"][row["dish"]]["recipe"]
                            )
                            - place["return_minutes"]
                        ),
                    ),
                }
            )
            waste_cost += (packs * item["pack_g"] - remaining) * item["quotes"][market][
                "price_per_g"
            ]
    trip_cost = sum(config["markets"][market]["trip_cost"] for market in used_markets)
    at_risk = {
        name: dish["confirmed"] - quantities[name]
        for name, dish in config["dishes"].items()
        if quantities[name] < dish["confirmed"]
    }
    expired = {
        name: item["stock"]
        for name, item in config["ingredients"].items()
        if item["stock"] and item["use_by"] < config["date"]
    }
    return {
        "feasible": not blockers,
        "blockers": blockers,
        "questions": sorted(set(questions)),
        "menu": menu,
        "prep": prep,
        "buying": purchases,
        "stock_reservations": stock_allocations,
        "confirmed_at_risk": at_risk,
        "expired_stock": expired,
        "economics": {
            "revenue_after_discounts_fees_packaging": revenue,
            "ingredient_cost": ingredient_cost,
            "trip_cost": trip_cost,
            "expected_contribution": revenue - ingredient_cost - trip_cost,
            "purchase_surplus_cost_at_risk": waste_cost,
        },
        "assumptions": [
            "INR paise and grams; trips charged once per market.",
            "Forecast is a mean of comparable service days; confirmed orders are a minimum total demand.",
            "Purchase packs charged in full this shift; remaining stock may carry forward.",
            "Prep is completed before service. Supplier quotes and stock require kitchen updates.",
            "Rent, salaries, utilities and tax excluded from contribution.",
        ],
    }


def plan(config, demand):
    validate(config)
    options = []
    # Six dishes keep full menu subset enumeration small (at most 64 plans).
    names = list(config["dishes"])
    if len(names) > 10:
        raise ValueError("Prototype supports at most 10 dishes")
    for active in product((False, True), repeat=len(names)):
        quantities = {
            name: max(config["dishes"][name]["confirmed"], demand[name]["quantity"])
            if use
            else 0
            for name, use in zip(names, active)
        }
        result = calculate(config, demand, quantities)
        if result["feasible"]:
            options.append(result)
    options.sort(
        key=lambda row: (
            sum(row["confirmed_at_risk"].values()),
            -row["economics"]["expected_contribution"],
        )
    )
    chosen = options[0]
    baseline = calculate(
        config,
        demand,
        {
            name: max(dish["confirmed"], demand[name]["quantity"])
            for name, dish in config["dishes"].items()
        },
    )
    chosen["baseline_blockers"] = baseline["blockers"]
    chosen["baseline_ingredient_commitment"] = baseline["economics"]["ingredient_cost"]
    chosen["questions"] = sorted(set(baseline["questions"] + chosen["questions"]))
    chosen["alternatives"] = [
        {
            "portions": {item["dish"]: item["portions"] for item in row["menu"]},
            "economics": row["economics"],
            "confirmed_at_risk": row["confirmed_at_risk"],
        }
        for row in options[1:4]
    ]
    return chosen
