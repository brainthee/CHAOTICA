# Connected Apps (OAuth2 sign-in)

A **Connected App** is a separate application that signs people in with their
own CHAOTICA account and then uses the [REST API](../development/api_v1.md) as
them. The standalone LCARS UI is one example.

Each app sees exactly what the signed-in person could see in CHAOTICA, and no
more.

## Turning it on

1. **Settings → Access → Authentication:** enable `API_OAUTH2_ENABLED`. While
   this is off, `/o/` returns 404 and bearer tokens are ignored.
2. **Settings → Connected Apps → Add**. This requires the
   `manage_site_settings` permission. Fill in:

   | Field | What to enter |
   |---|---|
   | **Name** | Shown to people on the consent screen and in their profile. |
   | **Redirect URIs** | The app's callback URL(s), one per line. These must match exactly and use `https`; `http` is accepted in development only. |
   | **Allowed origins** | The origin the app runs on, e.g. `https://lcars.example.com`. Browsers on these origins may call the API and token endpoints. Leave it empty for apps that don't run in a browser. |
   | **Trusted** | Skips the consent screen. Use it only for first-party apps you run. |

3. Give the generated **Client ID** to the app. There is no client secret:
   every Connected App is a public client using authorization code with PKCE.
   Password and client-credentials grants are not available.

Adding, changing or deleting an app is recorded in the activity log. Deleting
an app revokes every token issued to it.

## What people see

- **Signing in:** the app sends the person to CHAOTICA. They log in as usual
  (SSO or local), then approve the app, unless it is trusted.
- **Profile → Connected apps:** lists the apps a person has signed in to. They
  can disconnect any app, which revokes its tokens and closes its live
  connections.
- **Deactivated accounts:** when an account is deactivated, all its tokens are
  revoked.

## Security notes

- Access tokens last 1 hour. Refresh tokens last 30 days and rotate on use.
  Expired tokens are cleared by a daily cron job.
- Sign-in through an app is refused while an administrator is impersonating
  someone.
- Cross-origin requests never carry the CHAOTICA session cookie. Apps
  authenticate only with their bearer token.

## Deployment checklist

- Run `python manage.py migrate`, which creates the OAuth tables.
- Behind a load balancer, set `API_NUM_PROXIES` to the number of proxies in
  front of the app. Throttling relies on it to see real client IPs.
- Realtime updates across several app instances need a shared Redis channel
  layer.
