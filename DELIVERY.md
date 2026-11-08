# Delivery playbook — from booking to report

Everything public-facing reads its name, price and links from `brand.json`. Change it there, then run `python -m scripts.build_site`.

## The client journey

| # | Client | You |
|---|--------|-----|
| 1 | Lands on the site, reads the offer, opens the sample report | — |
| 2 | Clicks **Book your audit** → booking form: details, CSV upload, price, pays by card | — |
| 3 | Sees the thank-you page; Stripe emails a receipt | Tally emails you the submission |
| 4 | Gets your "got it" email within a few hours | Send the "got it" email (template below) |
| 5 | — | Run intake, check the report, save as PDF (≈20 min) |
| 6 | Receives the report email with PDF and summary | Send the delivery email (drafted for you) |
| 7 | Optional 15-min walkthrough | Walk them through it |
| 8 | — | Refund if under the guarantee; delete their data; founding clients: 30-day reminder |

---

## One-time setup (≈45 minutes, all free)

### 1. Stripe
Create an account at dashboard.stripe.com and complete business verification. In **Settings → Customer emails**, turn on **Successful payments** so clients get a receipt automatically.

### 2. Booking form (Tally, free plan)
Create a form at tally.so with these blocks, in this order:

1. **Title:** "Book your ad spend audit"
2. **Short text:** "This takes about 3 minutes. Have your CSV export ready (guide below)."
3. **Short answer** (required): Business name
4. **Website** (required): Your website
5. **Short answer** (required): Your name
6. **Email** (required): Email for your report
7. **Multiple choice** (required): Which platform? Meta (Facebook/Instagram) · Google Ads
8. **Dropdown** (required): Monthly ad spend: Under £1,000 · £1,000–£3,000 · £3,000–£10,000 · £10,000+
   - **Conditional logic:** if "Under £1,000" → show text "Thanks — at this spend level the audit isn't the best use of your money yet. We'd rather tell you now." and **hide everything below**.
9. **Number** (required): "What's the most you'd happily pay for one sale or lead? (£)"
10. **Text block:** the export steps for the chosen platform (copy from `EXPORT_GUIDE.md`; use conditional logic on question 7 to show only the relevant one)
11. **File upload** (required): "Upload your CSV export". Allowed: .csv, .xlsx. Max size 10 MB.
12. **Long answer** (optional): "Anything we should know? (e.g. 'the brand campaign is intentional')"
13. **Checkbox** (required): "I agree my data is used only to prepare this report and deleted after delivery."
14. **Checkbox** (optional): "Founding client: I'm happy to give 15 minutes of honest feedback after my free 30-day re-audit."
15. **Payment block:** connect your Stripe account, amount £99, GBP. *(Check Tally's current payment terms for any added fee before going live.)*

**Settings:**
- Self email notifications: **on** (to you).
- Thank-you page: custom (text below).
- Form name / link: use the working service name.

Paste the form's link into `brand.json` → `booking_url`, then rebuild the site.

### 3. Walkthrough booking (optional)
A free Calendly link (one 15-minute event type) or a Google Calendar booking page. Paste the link into `brand.json` → `walkthrough_url`.

### 4. Landing page hosting
**Free temporary address (until the domain is bought):** Cloudflare Pages.
1. Create a free Cloudflare account.
2. **Workers & Pages → Create → Pages → Upload assets**.
3. Project name: your working brand (this becomes `<name>.pages.dev`).
4. Upload the `site/public` folder → **Deploy**.
5. To update: run `python -m scripts.build_site`, then upload `site/public` again.

When the domain is bought: **Custom domains → Set up a domain** in the same Pages project.

---

## Copy to paste

### Thank-you page (Tally)
> **Thank you. We've received your file.**
> Your report will arrive by email within 2 working days. You'll also get a payment receipt from Stripe.
> If we need anything else, we'll email you from {contact email}.

### "Got it" email (send within a few hours)
> **Subject:** We've received your file
>
> Hi {first name},
>
> Thanks for booking. We've received your {Meta/Google} export for {business} and your report will be with you by {date}.
>
> If anything in the file looks incomplete we'll let you know today, so there's nothing more you need to do.
>
> Best,
> {your name}, {operator}

### Delivery email
Drafted automatically by `scripts.intake` at `clients/<slug>/reports/email-<date>.txt`, using that client's real figures. Attach the PDF and send. Read it through first.

### Refund (guarantee) email
Also drafted automatically when the avoidable spend found is below the guarantee threshold. **Refund in Stripe first** (Payments → the payment → Refund), then send.

---

## Per-client checklist

- [ ] Payment received in Stripe; submission received from Tally
- [ ] "Got it" email sent
- [ ] Download the CSV and run:
      `python -m scripts.intake "Business Name" path/to/export.csv --max-cpa 25 --email them@example.com --contact "First Last" --monthly-spend 3000 [--founding]`
- [ ] Open the report: do the figures make sense? Anything odd in the export (wrong date range, campaign-level instead of ad-level)?
- [ ] Ctrl+P → **Save as PDF** (enable "Background graphics")
- [ ] Send the delivery email with the PDF attached
- [ ] If the script said **ACTION: refund**, refund in Stripe before sending
- [ ] Delete the submission in Tally and `clients/<slug>/data/` (founding clients: keep until the re-audit unless they ask otherwise)
- [ ] Founding client: calendar reminder for day 30
- [ ] Log the client in your tracker (date, result, refund yes/no, testimonial yes/no)
