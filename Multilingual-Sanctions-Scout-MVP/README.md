# Multilingual Sanctions Scout · Showcase MVP

This is a local, browser-session demo of single-name screening and human review. It uses **fictional sample records only**. It is not connected to an official sanctions dataset and must not be used for operational screening.

## Run locally on Windows

### Prerequisites

- Windows 10 or 11.
- Node.js 20.9 or later. Node.js 24 LTS is recommended. The Windows installer includes npm.
- Internet access for the initial dependency install.
- A current browser such as Chrome or Edge.

### Start the app

1. Extract the project ZIP to a folder, for example `C:\Users\you\Documents\Multilingual-Sanctions-Scout-MVP`.
2. Open PowerShell in that extracted folder. Check that it contains `package.json`.
3. Confirm Node.js is available:

   ```powershell
   node --version
   npm.cmd --version
   ```

   If PowerShell blocks `npm`, use `npm.cmd` as shown below; do not change the machine execution policy.

4. Install dependencies:

   ```powershell
   npm.cmd ci
   ```

5. Start the local development server:

   ```powershell
   npm.cmd run dev
   ```

6. Open `http://localhost:3000` in Chrome or Edge. Keep PowerShell open while using the app. Press `Ctrl+C` in that window to stop it.

If port 3000 is already in use, run `npm.cmd run dev -- --port 3001` and open `http://localhost:3001`.

## Working showcase features

- Screen one name, alias, and original-script name against the bundled fictional examples.
- Set a 50–100 name similarity threshold and see ranked candidates with a deterministic similarity explanation.
- Search screening history for the current browser session.
- Open a candidate, assign a demo reviewer, record notes, change the human review status, and filter the case queue by status.
- Switch between the available English and Arabic interface labels and RTL layout.
- Print the screening report or choose **Save as PDF** in the browser print dialog.
- Toggle demo mode. With it off, the app returns a source-unavailable state instead of pretending that an official list was searched.

All screening and review state lives in browser memory and is cleared on reload. Submitted identifier fields are masked in saved screening details. Do not enter real personal information into this showcase.

## Source status and omitted features

The selected official source is the U.S. Treasury Office of Foreign Assets Control (OFAC) Specially Designated Nationals (SDN) List. OFAC publishes CSV and XML through its [Sanctions List Service](https://sanctionslist.ofac.treas.gov/Home/SdnList). In this showcase the source is **Not configured**. No OFAC records are downloaded or searched. The Manage List screen links to the official publisher and shows the unavailable import metadata. There is no refresh button because importing a list is not implemented.

The Supabase schema in `supabase/schema.sql` is a starter only; this showcase has no sign-in, role-based access control, server-side persistence, source importer, private report storage, or append-only server audit log. Review events are session-only and can be edited by the local user through the demo UI. PDF export uses the browser print dialog. These features are not represented as implemented.

## Matching limitations

The demonstration matcher normalizes Unicode and Arabic letter variants, compares names and aliases using sorted-token and Dice bigram similarity, and applies a fixed character-map transliterator for Arabic script. Transliteration is incomplete, is not translation, and must not be read as a probability of identity. The examples are fictional and the scores only exercise the interface.

This showcase is not production-ready and does not claim regulatory certification or guaranteed compliance.
