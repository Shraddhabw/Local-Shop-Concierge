# Demo script (3 minutes)

Replace `YOURDOMAIN` with the real domain. Run the "before you start" checklist first. Speak in the owner's and customer's words, not in technical terms.

## Before you start (5 minutes, not part of the 3)

- [ ] `https://YOURDOMAIN/healthz` shows `ok`; the padlock is present.
- [ ] Demo shops exist: `https://YOURDOMAIN/s/demo-salon` loads (if not: `docker compose exec app python scripts/seed.py --db /data/shop_concierge.db`).
- [ ] `AI_ENABLED=true` on the server and the import works once (or decide to skip step 2, see Fallbacks).
- [ ] A throwaway email address you can open during the demo; the Titan mailbox is working (`scripts/send_test_email.py`).
- [ ] The owner's email inbox (where the lead alert will arrive) open in another tab. Phone ready with the page open, or a second browser window sized like a phone.
- [ ] Copy the sample price list below into a text file ready to paste.

Sample price list to paste:

```
Sunrise Spa price list
Haircut 300 (30 min)
Facial 1,200 - 45 minutes
Head massage 400, 20 min
Open Mon-Sat 9am to 7pm, closed Sunday.
We accept UPI and cash. Parking is free.
```

## The 3 minutes

**0:00 - The owner registers (30 s).** "Meet Asha, she runs a small spa and has no time for the phone." Open `https://YOURDOMAIN`, click *Create your shop*, enter *Sunrise Spa*, an email and a password. "She gets a confirmation email." Click the link in the email, then log in. The dashboard opens with her shop name.

**0:30 - She imports her price list (45 s).** Click *Import*, paste the sample price list, click *Read my text*. "The AI reads it, but it only suggests." Show the preview: services with prices and minutes, hours Monday to Saturday, closed Sunday, an FAQ about UPI. Change one price to show it is editable, then *Confirm and save*. "Nothing was saved until she clicked confirm." The dashboard then opens with a green banner "Import saved: added ...".

**1:15 - A customer asks a price question (30 s).** Open her public page (`/s/sunrise-spa`) on the phone. Show the QR code and the WhatsApp button briefly. In the chat type *How much is a haircut?* The answer appears at once with the price. "This answer comes straight from her own price list, so it can't be made up."

**1:45 - An unanswered question becomes a lead (45 s).** Type *Do you do eyebrow threading?* The chat says it doesn't know and offers to take details. Fill in a name and phone, tick "I agree to share these details", send. "The customer chose to share this, so only now is Asha alerted." Switch to the inbox: the lead alert email arrives (usually within seconds).

**2:30 - The dashboard shows what happened (20 s).** Back on the dashboard: chats this week, 1 lead, and "Do you do eyebrow threading?" under questions the chat could not answer. Click *Suggest FAQ*, type "Yes, Saturdays only", click *Approve and add*. "Next time, the chat knows." A green banner "FAQ approved and added" confirms it.

**2:50 - Her own web address over HTTPS (10 s).** Open `https://sunrise-spa.YOURDOMAIN` (any shop works, e.g. `https://demo-salon.YOURDOMAIN`): same page, padlock, no setup.

**Closing line:** "Every question a busy owner can't answer in the moment is answered correctly, or turned into a customer who left their number, and the shop never promises something it doesn't offer."

## Fallbacks (say them calmly, they are features)

- **AI switched off or slow:** skip the import; add the services on the *Services* page instead (or have one pre-filled). Say: "The app works fully without AI; AI only helps with typing." The import page itself says "enter by hand" if the AI is unavailable.
- **Email is slow:** open the *Leads* page; the lead is already saved there. The alert email follows.
- **A certificate for a brand-new shop subdomain takes a few seconds on first visit:** open the subdomain once before the demo.
- **Never** type real customer data in the demo; use made-up names and numbers.
