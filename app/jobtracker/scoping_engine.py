"""Sandboxed evaluation of :class:`ScopingTemplate` calculations.

The engine turns captured answers into testing/reporting days and the hours that
populate a Phase. All arithmetic runs through :mod:`simpleeval` (no Python
execution, no attribute access, no imports) so admin-authored formulas and
imported scoping packs are safe to evaluate.

No organisation-specific rules live here: this module only knows *how* to
combine rates/weights and evaluate expressions, never the values themselves.
"""

import math
import logging
from decimal import Decimal

from simpleeval import EvalWithCompoundTypes, InvalidExpression

from .models.scoping import (
    ScopingFieldType,
    ScopingCalcRole,
    SizingCombine,
    CalcMode,
)

logger = logging.getLogger(__name__)


def round_half_up(num):
    """Round up to the nearest half (Blizzard's roundUpHalf)."""
    return math.ceil(float(num) * 2) / 2


def bucket(value, thresholds, values):
    """Tiered lookup: return ``values[i]`` for the first ``thresholds[i]`` that
    ``value`` does not exceed; falls back to the last value."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0
    for threshold, result in zip(thresholds, values):
        if value <= threshold:
            return result
    return values[-1] if values else 0


SAFE_FUNCTIONS = {
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
    "round_half_up": round_half_up,
    "max": max,
    "min": min,
    "abs": abs,
    "bucket": bucket,
}


class ScopingError(Exception):
    """Raised for user-facing calculation problems (bad formula, bad input)."""


def _num(value, default=0.0):
    try:
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _selected_option(field, raw_value):
    """Return the option dict matching ``raw_value`` for a SELECT field."""
    for opt in field.options or []:
        if str(opt.get("value")) == str(raw_value):
            return opt
    return None


def build_context(template, answers):
    """Build the variable namespace passed to expressions.

    Each field slug maps to a usable value (numbers for NUMBER/BOOLEAN,
    the selected value for SELECT). SELECT fields additionally expose
    ``<slug>_weight`` holding the chosen option's weight.
    """
    answers = answers or {}
    context = {}
    for field in template.fields.all():
        raw = answers.get(field.slug, field.default)
        if field.field_type == ScopingFieldType.BOOLEAN:
            context[field.slug] = bool(raw) and str(raw).lower() not in ("false", "0", "")
        elif field.field_type == ScopingFieldType.NUMBER:
            context[field.slug] = _num(raw)
        elif field.field_type == ScopingFieldType.SELECT:
            opt = _selected_option(field, raw)
            # expose numeric value if the option value is numeric, else string
            context[field.slug] = _num(raw, default=raw)
            context["{}_weight".format(field.slug)] = _num(opt.get("weight")) if opt else 0.0
        else:  # TEXT / TEXTAREA
            context[field.slug] = raw if raw is not None else ""
    return context


def _evaluate_expression(expression, names):
    evaluator = EvalWithCompoundTypes(functions=SAFE_FUNCTIONS, names=names)
    try:
        return float(evaluator.eval(expression))
    except InvalidExpression as exc:
        raise ScopingError("Invalid formula: {}".format(exc))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ScopingError("Formula could not be evaluated: {}".format(exc))


def _declarative_testing_days(template, answers, context, justification):
    """Compute testing days from field rates/weights.

    base = combine(sizing days) ; then + additive days ; then x (1 + multipliers)
    """
    sizing_days = []
    additive = 0.0
    multiplier = 0.0

    for field in template.fields.all():
        role = field.calc_role
        if role == ScopingCalcRole.SIZING and field.rate:
            value = _num(context.get(field.slug))
            rate = float(field.rate)
            if rate:
                days = value / rate
                sizing_days.append(days)
                justification.append(
                    "{}: {:g} ÷ {:g}/day = {:.2f} days".format(
                        field.label, value, rate, days
                    )
                )
        elif role == ScopingCalcRole.ADDITIVE:
            w = float(field.weight or 0)
            add = 0.0
            if field.field_type == ScopingFieldType.BOOLEAN:
                if context.get(field.slug):
                    add = w
            elif field.field_type == ScopingFieldType.SELECT:
                add = context.get("{}_weight".format(field.slug), 0.0)
            elif field.field_type == ScopingFieldType.NUMBER:
                add = _num(context.get(field.slug)) * w
            if add:
                additive += add
                justification.append("+ {:g} days for {}".format(add, field.label))
        elif role == ScopingCalcRole.MULTIPLIER:
            w = float(field.weight or 0)
            frac = 0.0
            if field.field_type == ScopingFieldType.BOOLEAN:
                if context.get(field.slug):
                    frac = w
            elif field.field_type == ScopingFieldType.SELECT:
                frac = context.get("{}_weight".format(field.slug), 0.0)
            elif field.field_type == ScopingFieldType.NUMBER:
                frac = _num(context.get(field.slug)) * w
            if frac:
                multiplier += frac
                justification.append("+ {:.0f}% for {}".format(frac * 100, field.label))

    if sizing_days:
        if template.sizing_combine == SizingCombine.SUM:
            base = sum(sizing_days)
        else:
            base = max(sizing_days)
    else:
        base = 0.0

    return (base + additive) * (1 + multiplier)


def evaluate(template, answers):
    """Evaluate a template against a set of answers.

    Returns a dict with testing_days, reporting_days, delivery_hours,
    reporting_hours, justification (list of str) and errors (list of str).
    Never raises for calculation issues; collects them in ``errors``.
    """
    from constance import config

    result = {
        "testing_days": 0.0,
        "reporting_days": 0.0,
        "delivery_hours": 0.0,
        "reporting_hours": 0.0,
        "justification": [],
        "errors": [],
    }
    justification = []

    # Required-field validation
    for field in template.fields.all():
        if field.required:
            val = (answers or {}).get(field.slug, field.default)
            if val in (None, ""):
                result["errors"].append("{} is required".format(field.label))

    context = build_context(template, answers)

    try:
        if template.calc_mode == CalcMode.EXPRESSION:
            if not template.testing_expression.strip():
                raise ScopingError("No testing formula configured")
            testing = _evaluate_expression(template.testing_expression, context)
            justification.append(
                "Testing: {}".format(template.testing_expression.strip())
            )
        else:
            testing = _declarative_testing_days(
                template, answers, context, justification
            )
    except ScopingError as exc:
        result["errors"].append(str(exc))
        return result

    testing = max(testing, 0.0)

    # Reporting days: macro takes precedence, else the fallback expression
    try:
        rep_names = dict(context)
        rep_names["testing_days"] = testing
        if template.reporting_macro:
            reporting = _evaluate_expression(
                template.reporting_macro.expression, rep_names
            )
        elif template.reporting_expression.strip():
            reporting = _evaluate_expression(
                template.reporting_expression, rep_names
            )
        else:
            reporting = 0.0
    except ScopingError as exc:
        result["errors"].append(str(exc))
        reporting = 0.0

    reporting = max(reporting, 0.0)

    hours_per_day = float(getattr(config, "DEFAULT_HOURS_IN_DAY", 7.5) or 7.5)

    result.update(
        {
            "testing_days": round(testing, 2),
            "reporting_days": round(reporting, 2),
            "delivery_hours": round(testing * hours_per_day, 2),
            "reporting_hours": round(reporting * hours_per_day, 2),
            "justification": justification,
        }
    )
    return result
