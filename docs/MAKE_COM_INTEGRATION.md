# Wiring Make.com into the dashboard

The dashboard is fed by two webhook endpoints. Nothing in the existing PWYS registration →
SMS scenario needs to be redesigned — this adds two new HTTP modules that fire alongside
what's already there.

Both endpoints require `Authorization: Bearer <INGEST_API_KEY>` (the value set in the
dashboard's environment config). Use a Make.com **HTTP → Make a request** module, method
`POST`, body type JSON.

## 1. Logging an outbound SMS send

Add this HTTP module immediately after each Twilio "Create a Message" module — in the
Registration Automation scenario (both outbound messages) and in the Game Day scenario.
Set `message_type` per send point so the dashboard can break activity down by type:

- Registration Automation, message 1 (registration confirmation) → `"registration"`
- Registration Automation, message 2 (weekly practice schedule) → `"weekly_practice"`
- Game Day scenario → `"game_day"`
- Cancellation Notice scenario (see section 4 below) → `"cancellation"`

`POST https://pwys.revupwithai.com/api/ingest/sms`

```json
{
  "contact_phone": "{{Responsible Party Phone Number}}",
  "direction": "outbound",
  "status": "sent",
  "location": "{{Locations → Text}}",
  "message_type": "registration",
  "monday_item_id": "{{Monday item ID}}",
  "twilio_sid": "{{Twilio message Sid}}",
  "body": "{{message body}}"
}
```

Use the confirmed field paths from the existing scenario — `phone_mm63qf51 → text` for
phone, `Locations → Text` for location (not the "Location of Next Practice (Automation
Only)" field, which is blank ~50% of the time). `message_type` must be one of
`registration`, `weekly_practice`, `game_day`, `cancellation` — omit it (or leave blank)
for any send that doesn't fit one of those, the dashboard still counts it toward total
SMS sent, just not toward a specific type card.

## 2. Logging an inbound SMS reply (including STOP)

Add this on the scenario that watches Twilio's inbound webhook / "Watch Incoming Messages"
trigger.

`POST https://pwys.revupwithai.com/api/ingest/sms`

```json
{
  "contact_phone": "{{From}}",
  "direction": "inbound",
  "status": "received",
  "body": "{{Body}}"
}
```

`location` and `monday_item_id` can be omitted here if not readily available on the
inbound trigger — the dashboard will still count the reply, just without a location
breakdown for that row.

## 3. Logging Robly email sends/opens/clicks (once Keith delivers API credentials)

This is parked until Robly credentials land (see handoff doc — blocked on Keith). Once
the Robly HTTP module is added to Make.com per the existing plan, add a matching call:

`POST https://pwys.revupwithai.com/api/ingest/email`

```json
{
  "email": "{{contact email}}",
  "event_type": "sent",
  "location": "{{Locations → Text}}",
  "robly_contact_id": "{{Robly contact id}}",
  "subject": "{{subject line}}"
}
```

Robly's opens/clicks are typically delivered via their own webhook or a polling report —
whichever mechanism is used, map it to `event_type: "opened"` / `"clicked"` /
`"bounced"` / `"unsubscribed"` on the same endpoint.

## 4. Dashboard-triggered cancellation notices

The dashboard has a "Send cancellation notice" button (`/cancellations/new`) that a staff
member uses to blast a cancellation text to everyone registered at one location. It does
**not** talk to Twilio or monday.com directly — it POSTs to a new Make.com **Custom
webhook** scenario, which reuses the existing Twilio and monday.com connections to do the
actual lookup and send. This is the "Cancellation Notice" scenario; it's separate from
the Registration Automation and Game Day scenarios and doesn't touch them.

Dashboard → Make.com webhook payload:

```json
{
  "location": "Kroc Center",
  "message": "Practice is cancelled today. We'll see you next time! / La practica de hoy esta cancelada. Nos vemos la proxima vez!",
  "triggered_by": "ryates051@gmail.com"
}
```

The scenario should:

1. Trigger on the custom webhook.
2. List the monday.com board's items, filtered to where `Locations → Text` equals the
   incoming `location`.
3. For each matching item, send an SMS via Twilio (`to` = `phone_mm63qf51 → text`,
   `body` = the incoming `message`, verbatim — the dashboard form already lets staff
   review it before sending, so don't template or translate it further).
4. After each Twilio send, log it with an **Ingest SMS** HTTP module exactly like the
   Game Day scenario's, with `"message_type": "cancellation"`.

The webhook's URL goes into the dashboard's `CANCELLATION_WEBHOOK_URL` environment
variable on Railway. Until that's set, the "Send cancellation notice" page will show an
error instead of silently failing.

## Notes

- Both endpoints are idempotent on `twilio_sid` for SMS — if Make.com retries a webhook
  after a timeout, it won't double-count.
- `status` for SMS must be one of `sent`, `delivered`, `failed`, `received`.
- `event_type` for email must be one of `sent`, `opened`, `clicked`, `bounced`,
  `unsubscribed`.
- Do not log message bodies containing anything beyond what's already in Monday.com /
  Twilio — the `body` field exists for support/debugging visibility on the dashboard, not
  as a new place to store sensitive data.
