import os
import requests


RESEND_API_KEY = os.environ["RESEND_API_KEY"]
NOTIFICATION_EMAIL = "dinahoch@hotmail.co.uk"


def send_notification(flights: list[dict]) -> None:
    if not flights:
        return

    rows = ""
    for f in flights:
        rows += (
            f"<tr>"
            f"<td>{f['airline']}</td>"
            f"<td>{f['origin']} → {f['destination']}</td>"
            f"<td>{f['date']}</td>"
            f"<td>{f.get('departure_time', 'N/A')}</td>"
            f"<td>{f.get('price', 'N/A')}</td>"
            f"<td><a href='{f.get('url', '#')}'>Book</a></td>"
            f"</tr>"
        )

    html = f"""
    <h2>✈️ Flights found from Israel to Europe</h2>
    <p>2 adults + 1 infant, one-way, March 18–22 2026</p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">
      <thead>
        <tr>
          <th>Airline</th><th>Route</th><th>Date</th>
          <th>Departure</th><th>Price</th><th>Link</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    """

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": "Flight Checker <onboarding@resend.dev>",
            "to": [NOTIFICATION_EMAIL],
            "subject": f"🛫 {len(flights)} flight(s) found from Israel to Europe",
            "html": html,
        },
    )
    response.raise_for_status()
    print(f"Notification sent: {len(flights)} flight(s)")
