# Step 3.3 – engine random starts for golden_results.xlsx (seed 2025)

Paste the start below into the yellow cell **B17** of each MUS sheet. The selection table then fills itself and must equal the engine's selection (tests/golden/test_sampling_golden.py re-implements the sheet's COUNTIF rule and checks it).

Population: account_type = Expense, debit > 0. TM 280,000. Expected misstatement 10% of TM. RNG: numpy default_rng(seed); start = truncate(u x J, 0.01).

| Sheet | seed | n | J | Random start (B17) | Distinct lines selected | Top stratum |
|---|---|---|---|---|---|---|
| MUS_95 | 2025 | 161 | 77968.969378882 | **77536.85** | 149 | 8 items, AED 1,624,857.83 |
| MUS_90 | 2025 | 122 | 102893.475983607 | **102323.22** | 115 | 8 items, AED 1,624,857.83 |

Rules used are `pending_verification` (firm_methodology_v0.2 DRAFT). Regenerate this table if the Rules Library values change.
