# UAE public holidays – sources (data/uae_holidays_2025.csv)

Each date was verified on 27 Oct 2026 against official MoHRE private-sector announcements, which implement Cabinet Resolution 27 of 2024 on official holidays (see u.ae > Public holidays).

| Date(s) 2025 | Holiday | Source |
|---|---|---|
| 1 Jan (Wed) | New Year's Day | Fixed date under Cabinet Resolution 27/2024 (u.ae public holidays page) |
| 30 Mar – 1 Apr (Sun–Tue) | Eid Al Fitr | MoHRE, 19 Mar 2025 – https://mohre.gov.ae/en/media-center/news/19/3/2025/eid-al-fitr-holiday-announced-for-private-sector. Ramadan ran 29 days, so the conditional extension to 2 Apr did not apply. |
| 5 Jun (Thu) | Arafat Day | MoHRE, 29 May 2025 – https://www.mohre.gov.ae/en/media-centre/news/29/5/2025/eid-al-adha-holiday-announced-for-private-sector-from-5-june-to-8-june.aspx |
| 6–8 Jun (Fri–Sun) | Eid Al Adha | same MoHRE announcement, 29 May 2025; also WAM https://www.wam.ae/en/article/bjx2t1h-eid-al-adha-holiday-announced-for-private-sector |
| 27 Jun (Fri) | Hijri New Year 1447 | MoHRE, 16 Jun 2025 – https://mohre.gov.ae/ar/media-center/news/16/6/2025/mohre-declares-27-june-as-islamic-new-year-holiday-for-private-sector ; FAHR (federal government) same date |
| 5 Sep (Fri) | Prophet Muhammad's Birthday | MoHRE, 26 Aug 2025 – https://mohre.gov.ae/en/media-center/news/26/8/2025/uae-announces-5-september-as-public-holiday-for-private-sector-on-the-occasion-of-prophet ; FAHR circular 08/2025 |
| 1–2 Dec (Mon–Tue) | Eid Al Etihad (54th National Day) | MoHRE, 17 Nov 2025 – https://www.mohre.gov.ae/en/media-center/news/17/11/2025/54th-eid-al-etihad-1-and-2-december-2025-declared-as-official-holiday-for-the-private-sector |

**Notes**
- National Day was observed on 1–2 Dec, not 2–3 Dec. Some secondary sites published predicted dates; the CSV uses the MoHRE announcements throughout.
- Several holidays fall on Fri/Sat/Sun. They are still listed. The calendar engine records the reason as "holiday" before "weekend" where precedence requires it.
- **fy2021_2022.csv context:**
  - 1–3 Dec 2021 was the National Day/Commemoration Day holiday (MoHRE, 24 Nov 2021).
  - The weekend changed from Fri/Sat to Sat/Sun from 1 Jan 2022 (UAE government announcement, 7 Dec 2021; reported by WAM and Reuters).
  - 1 Jan 2022 was a holiday (New Year).
  - The generator avoids all of these dates, so only the weekend rule drives the FY21/22 flags.
- Islamic dates should be stored as 'Provisional' until announced (Build Guide 3.5). All 2025 dates above are confirmed.
