# Financial Health & Credit Assessment

**ICAI AI Certification Course (AICA) Level 2 - Module C Capstone Project**

Submitted by **CA Asmita Shreeram Hirlekar**, Chartered Accountant (Membership No. 190982) · Pune Branch · Batch 100, Pune

**Project:** a Streamlit decision-support application that takes six inputs about a borrower (monthly income, monthly debt payments, credit card limit, balance used, missed payments in the last 12 months, average age of accounts) and instantly returns an estimated credit score with its band, a debt-to-income check, a credit-utilisation check, a personalised action plan and a profile summary table.

**Video walkthrough:** [Google Drive video](https://drive.google.com/file/d/1D1lmrh_Fz02fp9O2dsXc6aYKn-CL6iyP/view?usp=sharing)

**Presentation:** [docs/Capstone_Presentation.pptx](docs/Capstone_Presentation.pptx)

## How it works

| Step | What happens |
|---|---|
| Input | Six fields in the sidebar: four number inputs and two sliders |
| Compute | Debt-to-income ratio = debt payments ÷ income; utilisation = balance used ÷ limit; estimated score = 850 − utilisation penalty (utilisation % × 1.8, max 200) − 50 per missed payment + account-age bonus (3 per year, max 50), clamped to 300–850 |
| Classify | Score band (Poor < 580, Fair, Good from 670, Very Good from 740, Exceptional from 800); DTI status (Healthy ≤ 36 %, Warning ≤ 43 %, High Risk); utilisation status (Optimal ≤ 30 %, High) |
| Advise | Rule-based action plan: amount to pay down to reach 30 % utilisation, automatic minimum payments if any payment was missed, debt consolidation if DTI > 40 % |
| Summarise | Profile summary table of every input |

Every number is computed by plain Python arithmetic. No model is trained, nothing is stored and no data leaves the machine. The score is indicative decision support, not a credit-bureau score.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501) and change any input in the sidebar; the dashboard recomputes instantly.

## Files

- `app.py` – the complete application (about 120 lines)
- `requirements.txt` – Python dependencies
- `docs/Capstone_Presentation.pptx` – the capstone presentation (14 slides)

## Technology

Python 3 · Streamlit (sidebar inputs, st.metric, st.columns, st.dataframe) · pandas · NumPy
