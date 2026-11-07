"""Synthetic merchant data. All quantities use grams and money uses paise."""

import csv
import json
from pathlib import Path


def seed(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    ingredients = {
        "rice": 6,
        "noodles": 9,
        "chilli": 30,
        "paneer": 35,
        "vegetables": 8,
        "sauce": 15,
    }
    dishes = [
        (
            "chilli-noodles",
            "Wok Street",
            "Chinese",
            24000,
            20,
            12,
            {"noodles": 150, "chilli": 15, "vegetables": 100, "sauce": 20},
        ),
        (
            "fried-rice",
            "Wok Street",
            "Chinese",
            22000,
            20,
            12,
            {"rice": 180, "vegetables": 100, "sauce": 20},
        ),
        (
            "paneer-bowl",
            "Bowl House",
            "Indian",
            26000,
            20,
            6,
            {"rice": 180, "paneer": 100, "chilli": 10},
        ),
        (
            "veg-bowl",
            "Bowl House",
            "Indian",
            20000,
            15,
            6,
            {"rice": 180, "vegetables": 150, "chilli": 5},
        ),
        (
            "paneer-wrap",
            "Bowl House",
            "Indian",
            23000,
            15,
            6,
            {"paneer": 100, "vegetables": 80, "chilli": 10},
        ),
        (
            "veg-wrap",
            "Bowl House",
            "Indian",
            18000,
            15,
            6,
            {"vegetables": 180, "sauce": 20},
        ),
    ]
    config = {
        "synthetic": True,
        "date": "2026-11-06",
        "timezone": "Asia/Kolkata",
        "as_of": "14:00",
        "service": "dinner",
        "service_start": "18:00",
        "service_end": "22:00",
        "markets": {
            "main": {
                "name": "Main Market",
                "opens": "06:00",
                "closes": "18:00",
                "arrival": "15:00",
                "return_minutes": 30,
                "trip_cost": 4000,
            },
            "other": {
                "name": "East Market",
                "opens": "08:00",
                "closes": "17:00",
                "arrival": "16:30",
                "return_minutes": 30,
                "trip_cost": 180000,
            },
        },
        "ingredients": {
            name: {
                "unit": "g",
                "stock": 0,
                "stock_cost_per_g": price,
                "use_by": "2026-11-06",
                "pack_g": 500 if name != "chilli" else 250,
                "quotes": {
                    "main": {"price_per_g": price, "available": True},
                    "other": {
                        "price_per_g": price + 2,
                        "available": None if name == "chilli" else True,
                    },
                },
            }
            for name, price in ingredients.items()
        },
        "cooks": {
            "mei": {
                "skills": ["Chinese"],
                "available": False,
                "start": "16:00",
                "end": "22:00",
            },
            "asha": {
                "skills": ["Indian"],
                "available": True,
                "start": "16:00",
                "end": "22:00",
            },
        },
        "dishes": {
            name: {
                "brand": brand,
                "skill": skill,
                "price": price,
                "discount": 1000,
                "fee": 5000,
                "packaging": 1500,
                "batch_size": 6,
                "batch_minutes": minutes,
                "recipe": recipe,
                "confirmed": 0,
                "sample_demand": demand,
            }
            for name, brand, skill, price, minutes, demand, recipe in dishes
        },
    }
    config["ingredients"]["rice"]["stock"] = 3500
    (folder / "kitchen.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    with (folder / "orders.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "order_id",
                "platform",
                "dish",
                "ordered_at",
                "zone",
                "quantity",
                "revenue",
                "discount",
                "fees",
                "service",
            ],
        )
        writer.writeheader()
        for day in ("2026-10-16", "2026-10-23", "2026-10-30"):
            for i, (name, dish) in enumerate(config["dishes"].items()):
                for service, hour in (("lunch", 13), ("dinner", 19)):
                    q = dish["sample_demand"] if service == "dinner" else 6
                    writer.writerow(
                        dict(
                            order_id=f"{day}-{i}-{service}",
                            platform="Swiggy" if i % 2 else "Zomato",
                            dish=name,
                            ordered_at=f"{day}T{hour}:00:00+05:30",
                            zone="Demo Zone",
                            quantity=q,
                            revenue=q * dish["price"],
                            discount=q * dish["discount"],
                            fees=q * dish["fee"],
                            service=service,
                        )
                    )
    return config
