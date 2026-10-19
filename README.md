# Dad's 80th · Edinburgh 2027

Static family trip page. `index.html` is generated, so edit `data.json`, then:

    python3 build.py            # rebuild locally
    python3 build.py --publish  # rebuild + push (GitHub Pages)

Public page: names, RSVP status and booking checkboxes only. No contact details.

## Chat (email-fed)
Family members tap Send on the Chat tab → their email app opens a message to the RSVP inbox
(subject "Dad's 80th chat: <name>"). To post it:

    python3 build.py --add-chat "Name" "message" [--date 2026-10-20T14:05] --publish

Emails/phone numbers in chat text are stripped automatically.
