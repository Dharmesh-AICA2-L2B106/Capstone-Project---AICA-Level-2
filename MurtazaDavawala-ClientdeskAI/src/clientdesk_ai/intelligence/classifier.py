"""Offline Local ML Service Category Recommendation Engine.

Uses lightweight TF-IDF text vectorization and multinomial classification
(with deterministic fallback) to suggest one of the 6 approved service groups
based on client business inquiries or onboarding remarks.
Enforces an abstention threshold (minimum 65% confidence).
"""

import math
import re
from typing import Dict, List, Optional, Tuple

APPROVED_SERVICE_GROUPS = [
    "GST",
    "ITR",
    "Company Formation",
    "Partnership Registration",
    "LLP Incorporation",
    "MCA Annual Compliance",
]

# Training corpus mapped strictly to the approved 6 service groups
TRAINING_DATA = [
    # GST
    ("Need new GST registration for trading business turnover exceeding limit", "GST"),
    ("Apply for GST number for proprietorship firm supplying goods", "GST"),
    ("GSTR-9 annual return compilation and GSTR-9C reconciliation audit", "GST"),
    ("GST monthly filing and vendor input tax credit mismatch resolution", "GST"),
    ("GSTR-9 annual return and GSTR-9C ITC reconciliation for regular taxpayer", "GST"),
    ("GSTR-1 and GSTR-3B monthly compliance outward taxable supply", "GST"),
    ("Casual taxable person GST registration for trade exhibition", "GST"),
    # ITR
    ("Salary income tax return Form 16 filing with house property loss", "ITR"),
    ("ITR-1 Sahaj filing for salaried individual with interest income", "ITR"),
    ("ITR-3 business tax return for proprietary trading firm with balance sheet", "ITR"),
    ("Presumptive taxation return section 44ADA for freelance IT consultant", "ITR"),
    ("Capital gains from sale of shares mutual funds and property tax filing", "ITR"),
    # Company Formation
    ("Incorporate private limited company with 2 directors on MCA SPICe+", "Company Formation"),
    ("One Person Company OPC registration name approval and MOA AOA drafting", "Company Formation"),
    ("Start a software startup Pvt Ltd company with authorized capital", "Company Formation"),
    ("Company incorporation including DIN PAN TAN EPFO ESIC registration", "Company Formation"),
    # Partnership Registration
    ("Partnership firm deed drafting and registration with Registrar of Firms ROF", "Partnership Registration"),
    ("Register partnership firm with 3 partners sharing profits equally", "Partnership Registration"),
    ("Form 1 partnership firm registration stamp duty and notarization", "Partnership Registration"),
    # LLP Incorporation
    ("LLP incorporation agreement Form 3 filing and designated partner consent", "LLP Incorporation"),
    ("Limited liability partnership formation with partner contribution", "LLP Incorporation"),
    ("RUN LLP name reservation and incorporation on MCA portal", "LLP Incorporation"),
    # MCA Annual Compliance
    ("Annual ROC compliance Form AOC-4 financial statements and MGT-7 annual return", "MCA Annual Compliance"),
    ("Director KYC DIR-3 verification and annual general meeting minutes", "MCA Annual Compliance"),
    ("Statutory MCA filings for private limited company balance sheet adoption", "MCA Annual Compliance"),
    ("Company annual ROC return filing auditor tenure and board report", "MCA Annual Compliance"),
]


class LocalServiceClassifier:
    """Offline, deterministic TF-IDF classifier with confidence thresholding."""

    def __init__(self, confidence_threshold: float = 0.65):
        self.threshold = confidence_threshold
        self.vocabulary: Dict[str, int] = {}
        self.class_priors: Dict[str, float] = {}
        self.word_weights: Dict[str, Dict[str, float]] = {g: {} for g in APPROVED_SERVICE_GROUPS}
        self.is_trained = False
        self.train(TRAINING_DATA)

    def _tokenize(self, text: str) -> List[str]:
        words = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())
        stopwords = {"and", "for", "with", "the", "in", "of", "to", "or", "on", "a", "an", "at", "by"}
        return [w for w in words if w not in stopwords]

    def train(self, corpus: List[Tuple[str, str]]) -> None:
        doc_count = len(corpus)
        if doc_count == 0:
            return

        class_counts: Dict[str, int] = {g: 0 for g in APPROVED_SERVICE_GROUPS}
        term_doc_freq: Dict[str, int] = {}

        for text, group in corpus:
            if group in class_counts:
                class_counts[group] += 1
            tokens = set(self._tokenize(text))
            for t in tokens:
                term_doc_freq[t] = term_doc_freq.get(t, 0) + 1

        # Calculate priors
        for g, count in class_counts.items():
            self.class_priors[g] = count / doc_count

        # Calculate TF-IDF term weights per category
        for text, group in corpus:
            if group not in APPROVED_SERVICE_GROUPS:
                continue
            tokens = self._tokenize(text)
            for t in tokens:
                tf = tokens.count(t) / len(tokens)
                idf = math.log((doc_count + 1) / (term_doc_freq.get(t, 1) + 1)) + 1
                self.word_weights[group][t] = self.word_weights[group].get(t, 0.0) + (tf * idf)

        self.is_trained = True

    def predict(self, client_inquiry_text: str) -> Tuple[Optional[str], float, str]:
        """
        Predict service category with confidence score.
        Returns: (predicted_group, confidence_score, explanation)
        Abstains if confidence is below self.threshold.
        """
        if not self.is_trained or not client_inquiry_text.strip():
            return None, 0.0, "Insufficient inquiry text for automated classification."

        tokens = self._tokenize(client_inquiry_text)
        if not tokens:
            return None, 0.0, "No meaningful keywords identified. Please select manually."

        scores: Dict[str, float] = {}
        for group in APPROVED_SERVICE_GROUPS:
            score = math.log(self.class_priors.get(group, 0.01))
            matched_weight = 0.0
            for t in tokens:
                weight = self.word_weights[group].get(t, 0.0)
                matched_weight += weight

            # Combine prior with keyword evidence
            scores[group] = score + (matched_weight * 2.5)

        # Softmax normalization to obtain confidence probability
        max_score = max(scores.values())
        exp_scores = {g: math.exp(s - max_score) for g, s in scores.items()}
        sum_exp = sum(exp_scores.values())
        probabilities = {g: round(val / sum_exp, 3) for g, val in exp_scores.items()}

        best_group = max(probabilities, key=probabilities.get)
        confidence = probabilities[best_group]

        # Transparent Abstention Gate
        if confidence < self.threshold:
            return (
                None,
                confidence,
                f"Confidence ({confidence*100:.1f}%) is below {self.threshold*100:.0f}% threshold. Selection requires human confirmation."
            )

        explanation = f"Matched keywords with {confidence*100:.1f}% confidence based on approved {best_group} compliance patterns."
        return best_group, confidence, explanation
