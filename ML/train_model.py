
import os
import random

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "invoice_data.csv")
MODEL_PATH = os.path.join(BASE_DIR, "model.joblib")

FEATURES = [
    "invoice_amount",
    "prev_late_count",
    "prev_ontime_count",
    "avg_delay_days",
    "payment_terms",
    "days_until_due",
]


def generate_dataset(rows=3000):
    
    random.seed(42)
    data = []

    for _ in range(rows):
        amount = round(random.uniform(1000, 100000), 2)
        late = random.randint(0, 10)
        ontime = random.randint(0, 15)
        avg_delay = round(random.uniform(0, 20), 1) if late > 0 else 0.0
        terms = random.choice([15, 30, 45, 60])
        days_left = random.randint(-10, terms)

        
        chance = 0.10
        total = late + ontime
        if total > 0:
            chance += 0.5 * (late / total)   
        chance += min(avg_delay, 20) / 100   
        if amount > 50000:
            chance += 0.10                   
        if days_left < 5:
            chance += 0.10                   
        chance = min(chance, 0.95)
        
        score = chance + random.uniform(-0.08, 0.08)
        is_late = 1 if score > 0.5 else 0

       
        data.append([amount, late, ontime, avg_delay, terms, days_left, is_late])

    return pd.DataFrame(data, columns=FEATURES + ["is_late"])


def train():
   
    df = generate_dataset()
    df.to_csv(CSV_PATH, index=False)
    print("Dataset ban gaya:", len(df), "rows")

    X = df[FEATURES]
    y = df["is_late"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = DecisionTreeClassifier(max_depth=5, random_state=42)
    model.fit(X_train, y_train)


    y_pred = model.predict(X_test)
    print("\nAccuracy:", round(accuracy_score(y_test, y_pred), 3))
    print("\nPrecision / Recall / F1-score:")
    print(classification_report(y_test, y_pred, target_names=["On Time", "Late"]))

    
    joblib.dump(model, MODEL_PATH)
    print("Model save ho gaya:", MODEL_PATH)


if __name__ == "__main__":
    train()