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
- Cancellation Notice scenario (see section 4 below) → `"cancellation"` or `"practice_on"`
  (the scenario's webhook now carries a `message_type` field the dashboard sets per
  notice type — map the Ingest SMS module's `message_type` to `{{message_type}}` from
  the webhook trigger, don't hardcode it)
- Move Indoors Notice scenario (see section 5 below) → `"move_indoors"`

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
`registration`, `weekly_practice`, `game_day`, `cancellation`, `move_indoors`,
`practice_on` — omit it (or leave blank) for any send that doesn't fit one of those, the
dashboard still counts it toward total SMS sent, just not toward a specific type card.

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

## 4. Dashboard-triggered cancellation / "soccer is on" notices

The dashboard has a "Send notice" page (`/notices/new`) that a staff member uses to blast
a text to everyone registered at one or more selected locations (a "Select all" shortcut
covers every location at once). Two notice types share this same targeting mechanism —
"Cancellation" and "Soccer is on" (a positive announcement that practice IS happening,
e.g. for a one-off return-to-play at a specific park/time) — distinguished only by the
message wording and the `message_type` tag the dashboard attaches. It does **not** talk
to Twilio or monday.com directly — it POSTs to a Make.com **Custom webhook** scenario,
which reuses the existing Twilio and monday.com connections to do the actual lookup and
send. This is the "Cancellation Notice" scenario; it's separate from the Registration
Automation and Game Day scenarios and doesn't touch them.

The webhook is protected with Make's API-key authentication (`x-make-apikey` header) —
the dashboard sends it on every request, so this endpoint isn't callable by anyone who
just finds the URL.

Dashboard → Make.com webhook request:

```
POST https://hook.us2.make.com/<webhook id>
x-make-apikey: <the key configured on the webhook>
Content-Type: application/json

{
  "locations": ["Kroc Center", "Treadwell Park"],
  "message": "Practice is cancelled today. We'll see you next time! / La practica de hoy esta cancelada. Nos vemos la proxima vez!",
  "triggered_by": "ryates051@gmail.com",
  "message_type": "cancellation"
}
```

`locations` is always a non-empty array — the dashboard requires at least one location
to be checked before it will submit. To reach everyone, staff use the "Select all"
shortcut, which just checks every location box (still sent as an explicit array, not a
special "all" value). `message_type` is either `"cancellation"` or `"practice_on"`
depending on which notice type staff picked on the form.

The scenario:

1. Triggers on the custom webhook (API-key auth required).
2. Lists the monday.com board's items (limit 500, so it doesn't miss registrations —
   the location filter happens downstream, not on this module).
3. Filters to where `Locations → Text` is one of the incoming `locations` (array:contain),
   then sends an SMS via Twilio (`to` = `phone_mm63qf51 → text`, `body` = the incoming
   `message`, verbatim — the dashboard form already lets staff review it before sending,
   so don't template or translate it further).
4. After each Twilio send, logs it with an **Ingest SMS** HTTP module exactly like the
   Game Day scenario's, with `"message_type": {{message_type}}` mapped from the incoming
   webhook field (not hardcoded — this is what lets the same scenario serve both notice
   types and still show up correctly on the dashboard's per-type tiles).

Two environment variables on Railway wire the dashboard to this webhook:
`CANCELLATION_WEBHOOK_URL` (the webhook URL) and `CANCELLATION_WEBHOOK_API_KEY` (the
matching API key). Until both are set, the "Send notice" page shows a clear error
instead of silently failing.

**Admin-defined notice types** (Settings → Notice Types in the dashboard) and
**recurring notices** (Settings → Recurring Notices) both go through this exact same
webhook too — a `message_type` of anything other than `cancellation` just means it came
from one of those instead of the built-in Cancellation type. Recurring notices don't
need a Make.com scenario of their own: the dashboard keeps its own schedule internally
and calls this webhook when one is due, the same way a staff member's "Send now" click
does. Nothing in Make.com needs to change when PWYS adds a new notice type or recurring
notice — that's the point.

## 5. Dashboard-triggered "move indoors" notices

Same dashboard page (`/notices/new`, "Notice type" set to "Move indoors") also blasts a
text to every registered family **except** whichever locations staff checked off — e.g.
"activity is cancelled but you can move indoors, except at Parkway Village and Jackson
Elementary." This is its own Make.com **Custom webhook** scenario ("Move Indoors
Notice"), API-key protected the same way, separate from every other scenario.

Dashboard → Make.com webhook request:

```
POST https://hook.us2.make.com/<webhook id>
x-make-apikey: <the key configured on the webhook>
Content-Type: application/json

{
  "excluded_locations": ["Parkway Village", "Jackson Elementary"],
  "message": "This week's activity is cancelled due to weather, but you can move indoors! / La actividad de esta semana esta cancelada por el clima, pero pueden moverse adentro!",
  "triggered_by": "ryates051@gmail.com"
}
```

`excluded_locations` can be an empty array — that means send to every location, no
exceptions.

The scenario:

1. Triggers on the custom webhook (API-key auth required).
2. Lists the monday.com board's items (limit 500, same reasoning as the cancellation
   scenario).
3. Filters to items whose `Locations → Text` is **not** one of the incoming
   `excluded_locations`, then sends an SMS via Twilio (`to` = `phone_mm63qf51 → text`,
   `body` = the incoming `message`, verbatim).
4. After each Twilio send, logs it with an **Ingest SMS** HTTP module, with
   `"message_type": "move_indoors"`.

Two more environment variables on Railway wire this one up: `MOVE_INDOORS_WEBHOOK_URL`
and `MOVE_INDOORS_WEBHOOK_API_KEY`.

## Notes

- Both endpoints are idempotent on `twilio_sid` for SMS — if Make.com retries a webhook
  after a timeout, it won't double-count.
- `status` for SMS must be one of `sent`, `delivered`, `failed`, `received`.
- `event_type` for email must be one of `sent`, `opened`, `clicked`, `bounced`,
  `unsubscribed`.
- Do not log message bodies containing anything beyond what's already in Monday.com /
  Twilio — the `body` field exists for support/debugging visibility on the dashboard, not
  as a new place to store sensitive data.
