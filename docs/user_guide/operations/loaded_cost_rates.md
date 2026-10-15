# Loaded Cost Rates

**Operations → Loaded Cost Rates** is the one place to view and set people's
loaded cost rates (LCR) across the site. Rates turn support budgets from money
into hours (see [Support-team budget](../Jobs/support_budget.md)).

## Who can use it

Everything on the page is gated on the **Can view loaded cost rates**
(`can_view_loaded_costs`) unit permission. The menu item only appears if you
hold it on at least one unit.

- **Seeing a rate.** You see the active members of every unit where you hold the
  permission. A superuser, or someone granted it globally, sees every unit.
- **Setting a rate.** You need the permission on *every* unit the person
  belongs to. Someone who is also in a unit outside your remit shows as
  **Read only**, and their other units are highlighted. This is the same rule
  as the API's `set-cost` action.
- **Your own rate.** Nobody can set their own rate (superusers excepted).

## Filtering

- **Organisational unit**: limit the list to one of your units. Each unit's
  **Support Teams** tab links here with that unit already selected.
- **Rate**: everyone, only people with no rate set, or only people with one.
- **Person**: search by name or email.

The table can also be sorted and searched in the page. A warning shows how many
people in the list have no rate: their support budgets can't be cashed out
until one is set.

## Setting a rate

Click **Set rate** to open the person's rate history and add a new rate:

- Rates are **date-effective**. Adding one keeps the earlier ones, so historical
  budgets and cash-outs keep the rate that applied at the time.
- Both the start date and the rate are required. The rate must be greater than
  zero.
- Each start date can only have one rate. To correct a rate, add a new one from
  a later date.

Every change is recorded in the Activity log.
