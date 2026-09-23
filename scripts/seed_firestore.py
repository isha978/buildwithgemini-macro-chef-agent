#!/usr/bin/env python3
"""Seed script for populating Firestore 'recipes' collection."""

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-02-4b6f07bf9464"

SAMPLE_RECIPES = [
    {
        "id": "lemon-garlic-chicken",
        "title": "Lemon Garlic Chicken & Spinach Skillet",
        "category": "Dinner",
        "prep_time_mins": 20,
        "calories": 420,
        "protein_g": 45.0,
        "carbs_g": 6.0,
        "fat_g": 18.0,
        "dietary_tags": ["dairy-free", "gluten-free", "low-carb", "high-protein"],
        "ingredients": ["chicken breast", "spinach", "garlic", "olive oil", "lemon juice", "salt", "pepper"],
        "instructions": "1. Season chicken breast with salt, pepper, and garlic. 2. Sear chicken in olive oil for 6 mins per side. 3. Add fresh spinach and lemon juice, cover until spinach wilts."
    },
    {
        "id": "herb-baked-salmon",
        "title": "Herb Crust Baked Salmon with Asparagus",
        "category": "Dinner",
        "prep_time_mins": 15,
        "calories": 510,
        "protein_g": 40.0,
        "carbs_g": 4.0,
        "fat_g": 32.0,
        "dietary_tags": ["dairy-free", "gluten-free", "keto", "high-protein"],
        "ingredients": ["salmon fillet", "asparagus", "olive oil", "dill", "parsley", "lemon"],
        "instructions": "1. Preheat oven to 400°F (200°C). 2. Toss asparagus in olive oil and arrange around salmon. 3. Top salmon with chopped herbs and lemon slices. 4. Bake for 12-15 minutes."
    },
    {
        "id": "berry-protein-oats",
        "title": "Vanilla Berry Vegan Protein Oats",
        "category": "Breakfast",
        "prep_time_mins": 10,
        "calories": 380,
        "protein_g": 30.0,
        "carbs_g": 48.0,
        "fat_g": 8.0,
        "dietary_tags": ["vegan", "dairy-free", "plant-based"],
        "ingredients": ["rolled oats", "plant-based protein powder", "almond milk", "blueberries", "chia seeds"],
        "instructions": "1. Cook oats in almond milk for 5 mins. 2. Stir in plant protein powder and chia seeds. 3. Top with fresh berries and enjoy."
    },
    {
        "id": "tofu-veggie-stir-fry",
        "title": "Crispy Tofu & Sesame Veggie Stir-Fry",
        "category": "Lunch",
        "prep_time_mins": 25,
        "calories": 410,
        "protein_g": 25.0,
        "carbs_g": 35.0,
        "fat_g": 20.0,
        "dietary_tags": ["vegan", "dairy-free", "gluten-free", "vegetarian"],
        "ingredients": ["firm tofu", "broccoli", "bell pepper", "tamari", "sesame oil", "ginger"],
        "instructions": "1. Press and cube tofu, pan-fry in sesame oil until golden. 2. Sauté broccoli and bell peppers. 3. Toss with tamari soy sauce and minced ginger."
    }
]


def seed_firestore():
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection("recipes")

    print(f"Seeding Firestore collection 'recipes' in project '{PROJECT_ID}'...")
    for recipe in SAMPLE_RECIPES:
        doc_id = recipe["id"]
        doc_data = {k: v for k, v in recipe.items() if k != "id"}
        collection_ref.document(doc_id).set(doc_data)
        print(f"  ✓ Seeded document 'recipes/{doc_id}': {doc_data['title']}")

    print("Firestore seeding completed successfully!")


if __name__ == "__main__":
    seed_firestore()
