
import os

import joblib
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model.joblib")


FEATURES = [
    "invoice_amount",
    "prev_late_count",
    "prev_ontime_count",
    "avg_delay_days",
    "payment_terms",
    "days_until_due",
]

LOW_LIMIT = 0.35    
HIGH_LIMIT = 0.65    

_model = None


def load_model():
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                "model.joblib nahi mila. Pehle 'python ml/train_model.py' chalao."
            )
        _model = joblib.load(MODEL_PATH)
    return _model


def get_risk_level(probability):
    """Probability se Low / Medium / High nikalta hai."""
    if probability < LOW_LIMIT:
        return "Low Risk"
    if probability <= HIGH_LIMIT:
        return "Medium Risk"
    return "High Risk"


def predict_late_payment(invoice_amount, prev_late_count, prev_ontime_count,
                         avg_delay_days, payment_terms, days_until_due):
    """Ek invoice ki details leke risk aur probability return karta hai."""
    model = load_model()

    row = pd.DataFrame(
        [[invoice_amount, prev_late_count, prev_ontime_count,
          avg_delay_days, payment_terms, days_until_due]],
        columns=FEATURES,
    )

    
    probability = float(model.predict_proba(row)[0][1])

    return {
        "risk_level": get_risk_level(probability),
        "late_payment_probability": round(probability, 3),
    }



if __name__ == "__main__":
    print(predict_late_payment(80000, 6, 2, 12, 30, 3))   
    print(predict_late_payment(5000, 0, 10, 0, 30, 25))   