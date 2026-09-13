"""Exhaustive regression suite for finance/templatetags/custom_filters.py.

Proves correct behavior of the four template filters (format_currency,
get_item, pending_summary, maqsad) and their fault tolerance: no filter may
ever raise on garbage input — a template rendering must never 500 because of
a filter.
"""
from decimal import Decimal

from django import template
from django.template import Context, Template
from django.test import TestCase
from django.utils import timezone

from finance.models import DailyReport, User
from finance.templatetags import custom_filters


def make_operator(username):
    return User.objects.create_user(username=username, password="pass12345", role="operator")


class FormatCurrencyTests(TestCase):
    """Exact output of format_currency for normal and boundary numeric values."""

    def test_none_returns_empty_string(self):
        self.assertEqual(custom_filters.format_currency(None), "")

    def test_zero_returns_zero(self):
        self.assertEqual(custom_filters.format_currency(0), "0")

    def test_zero_decimal_returns_zero(self):
        self.assertEqual(custom_filters.format_currency(Decimal("0.00")), "0")

    def test_million_space_separated(self):
        self.assertEqual(custom_filters.format_currency(1000000), "1 000 000")

    def test_thousand(self):
        self.assertEqual(custom_filters.format_currency(1000), "1 000")

    def test_decimal_rounds_half_to_even_via_float(self):
        # value is cast through float, so .5 rounds to even neighbour
        self.assertEqual(custom_filters.format_currency(Decimal("1234.5")), "1 234")
        self.assertEqual(custom_filters.format_currency(Decimal("1235.5")), "1 236")

    def test_decimal_fraction_below_half_rounds_down(self):
        self.assertEqual(custom_filters.format_currency(Decimal("1234.4")), "1 234")

    def test_float_fraction_rounds_to_nearest(self):
        self.assertEqual(custom_filters.format_currency(99.99), "100")
        self.assertEqual(custom_filters.format_currency(0.5), "0")
        self.assertEqual(custom_filters.format_currency(2.5), "2")

    def test_negative_amount(self):
        self.assertEqual(custom_filters.format_currency(-5000), "-5 000")

    def test_negative_fractional_no_minus_zero_crash(self):
        # never raises; documents the float-artifact output
        self.assertEqual(custom_filters.format_currency(-0.4), "-0")
        self.assertEqual(custom_filters.format_currency(-0.6), "-1")

    def test_string_numeric_converts(self):
        self.assertEqual(custom_filters.format_currency("12345"), "12 345")

    def test_string_with_surrounding_spaces_converts(self):
        self.assertEqual(custom_filters.format_currency("  7  "), "7")

    def test_bool_is_int_one(self):
        self.assertEqual(custom_filters.format_currency(True), "1")

    def test_huge_decimal_max_digits15(self):
        # largest value storable in max_digits=15 / decimal_places=2
        self.assertEqual(
            custom_filters.format_currency(Decimal("9999999999999.99")),
            "10 000 000 000 000",
        )

    def test_huge_float_no_crash(self):
        self.assertEqual(custom_filters.format_currency(12345678901234.56), "12 345 678 901 235")


class FormatCurrencyFaultToleranceTests(TestCase):
    """format_currency returns something (never raises) for garbage input."""

    def test_garbage_string_returned_as_is(self):
        self.assertEqual(custom_filters.format_currency("abc"), "abc")

    def test_whitespace_only_string_returned_as_is(self):
        self.assertEqual(custom_filters.format_currency("   "), "   ")

    def test_unicode_garbage_string_returned_as_is(self):
        self.assertEqual(custom_filters.format_currency("so'm €₽ — "), "so'm €₽ — ")

    def test_nan_does_not_raise(self):
        self.assertEqual(custom_filters.format_currency(float("nan")), "nan")

    def test_infinity_does_not_raise(self):
        self.assertEqual(custom_filters.format_currency(float("inf")), "inf")

    def test_bytestring_passthrough(self):
        self.assertEqual(custom_filters.format_currency(b"42"), "42")

    def test_empty_list_returned_as_is(self):
        self.assertEqual(custom_filters.format_currency([]), [])

    def test_arbitrary_object_returned_as_is(self):
        sentinel = object()
        self.assertIs(custom_filters.format_currency(sentinel), sentinel)

    def test_dict_returned_as_is(self):
        d = {"a": 1}
        self.assertIs(custom_filters.format_currency(d), d)


class GetItemTests(TestCase):
    """get_item: dict lookup with key-as-fallback, non-dict passthrough."""

    def test_dict_hit_returns_value(self):
        self.assertEqual(custom_filters.get_item({"a": 5}, "a"), 5)

    def test_dict_miss_returns_key_itself(self):
        # characterization: missing key falls back to the key, not None
        self.assertEqual(custom_filters.get_item({}, "missing"), "missing")

    def test_dict_miss_numeric_key(self):
        self.assertEqual(custom_filters.get_item({}, 7), 7)

    def test_falsy_value_is_returned_not_fallback(self):
        self.assertEqual(custom_filters.get_item({"a": 0}, "a"), 0)

    def test_non_dict_returns_key(self):
        self.assertEqual(custom_filters.get_item("not-a-dict", "k"), "k")
        self.assertEqual(custom_filters.get_item(None, "k"), "k")
        self.assertEqual(custom_filters.get_item(42, "k"), "k")
        self.assertEqual(custom_filters.get_item(["a"], "k"), "k")

    def test_unhashable_key_does_not_raise(self):
        self.assertEqual(custom_filters.get_item({}, ["x"]), ["x"])

    def test_int_key_looks_up_equivalent_int(self):
        self.assertEqual(custom_filters.get_item({1: "one"}, 1), "one")


class PendingSummaryTests(TestCase):
    """pending_summary: compact summary of non-zero currency amounts."""

    def test_none_returns_empty_string(self):
        self.assertEqual(custom_filters.pending_summary(None), "")

    def test_empty_dict_returns_empty_string(self):
        self.assertEqual(custom_filters.pending_summary({}), "")

    def test_all_zero_returns_empty_string(self):
        amounts = {"total_uzs": 0, "total_usd": 0, "total_rub": 0, "total_eur": 0}
        self.assertEqual(custom_filters.pending_summary(amounts), "")

    def test_all_none_returns_empty_string(self):
        amounts = {"total_uzs": None, "total_usd": None, "total_rub": None, "total_eur": None}
        self.assertEqual(custom_filters.pending_summary(amounts), "")

    def test_mixed_dict_exact_string(self):
        amounts = {"total_uzs": 60000, "total_usd": 0, "total_rub": 0, "total_eur": 5}
        self.assertEqual(custom_filters.pending_summary(amounts), "60 000 so'm, 5 €")

    def test_currency_order_uzs_usd_rub_eur(self):
        amounts = {"total_eur": 1, "total_rub": 2, "total_usd": 3, "total_uzs": 4}
        self.assertEqual(
            custom_filters.pending_summary(amounts), "4 so'm, 3 $, 2 ₽, 1 €"
        )

    def test_zero_entries_skipped(self):
        amounts = {"total_uzs": 0, "total_usd": 250, "total_rub": 0, "total_eur": 0}
        self.assertEqual(custom_filters.pending_summary(amounts), "250 $")

    def test_dict_instance_object_same_result(self):
        amounts = {"total_uzs": 60000, "total_usd": 0, "total_rub": 0, "total_eur": 5}
        report = DailyReport(
            type="income",
            date=timezone.now().date(),
            operator_id=None,
            category="x",
            total_uzs=Decimal("60000"),
            total_usd=Decimal("0"),
            total_rub=Decimal("0"),
            total_eur=Decimal("5"),
        )
        self.assertEqual(
            custom_filters.pending_summary(report),
            custom_filters.pending_summary(amounts),
        )

    def test_object_with_missing_attrs_treated_as_zero(self):
        class Pseudo:
            total_uzs = 0
            total_usd = None

        self.assertEqual(custom_filters.pending_summary(Pseudo()), "")

    def test_plain_object_without_attrs_returns_empty_string(self):
        self.assertEqual(custom_filters.pending_summary(object()), "")

    def test_garbage_amount_value_does_not_raise(self):
        # format_currency passes non-numeric garbage through, so the summary
        # contains the raw value — ugly but never a crash
        amounts = {"total_uzs": "abc", "total_usd": 0, "total_rub": 0, "total_eur": 0}
        self.assertEqual(custom_filters.pending_summary(amounts), "abc so'm")

    def test_unknown_keys_ignored(self):
        amounts = {"total_uzs": 1, "junk": 99, "total_gbp": 5}
        self.assertEqual(custom_filters.pending_summary(amounts), "1 so'm")

    def test_gbp_only_is_empty(self):
        self.assertEqual(custom_filters.pending_summary({"total_gbp": 5}), "")

    def test_scalar_input_returns_empty_string(self):
        for scalar in (0, "", "abc", 12345, True, [], [1], 0.0):
            with self.subTest(scalar=scalar):
                self.assertEqual(custom_filters.pending_summary(scalar), "")


class MaqsadTests(TestCase):
    """maqsad: extracts the kind from 'Maqsad: <kind>[ — <comment>]' desc."""

    def make_report(self, desc):
        return DailyReport(
            type="income",
            date=timezone.now().date(),
            operator_id=None,
            category="x",
            desc=desc,
        )

    def test_none_report_returns_empty_string(self):
        self.assertEqual(custom_filters.maqsad(None), "")

    def test_none_desc_returns_empty_string(self):
        self.assertEqual(custom_filters.maqsad(self.make_report(None)), "")

    def test_empty_desc_returns_empty_string(self):
        self.assertEqual(custom_filters.maqsad(self.make_report("")), "")

    def test_desc_without_prefix_returns_empty_string(self):
        self.assertEqual(custom_filters.maqsad(self.make_report("oddiy izoh")), "")

    def test_prefix_only_lowercase_kind(self):
        self.assertEqual(custom_filters.maqsad(self.make_report("Maqsad: foyda")), "foyda")

    def test_comment_after_em_dash_stripped(self):
        self.assertEqual(
            custom_filters.maqsad(self.make_report("Maqsad: xarajat — opt xarajat")),
            "xarajat",
        )

    def test_prefix_alone_returns_empty_string(self):
        self.assertEqual(custom_filters.maqsad(self.make_report("Maqsad:")), "")

    def test_kind_only_spaces_returns_empty_string(self):
        self.assertEqual(custom_filters.maqsad(self.make_report("Maqsad:    ")), "")

    def test_extra_spaces_after_colon(self):
        self.assertEqual(custom_filters.maqsad(self.make_report("Maqsad:   tushum")), "tushum")

    def test_leading_whitespace_before_prefix_is_not_matched(self):
        # starts with() is strict: leading whitespace means no prefix
        self.assertEqual(custom_filters.maqsad(self.make_report("  Maqsad: foyda")), "")

    def test_long_dash_comment_variant(self):
        # the code splits on em dash with spaces; a different dash is kept
        self.assertEqual(
            custom_filters.maqsad(self.make_report("Maqsad: chiqim -not: qaytim")),
            "chiqim -not: qaytim",
        )

    def test_unicode_and_punctuation_kind(self):
        self.assertEqual(
            custom_filters.maqsad(self.make_report("Maqsad: so'm qaytarish — 5%")),
            "so'm qaytarish",
        )

    def test_multi_word_kind_preserved(self):
        self.assertEqual(
            custom_filters.maqsad(self.make_report("Maqsad: kassa tashqarisi")),
            "kassa tashqarisi",
        )

    def test_case_sensitive_prefix(self):
        self.assertEqual(custom_filters.maqsad(self.make_report("maqsad: foyda")), "")
        self.assertEqual(custom_filters.maqsad(self.make_report("MAQSAD: foyda")), "")

    def test_object_without_desc_attr_returns_empty_string(self):
        self.assertEqual(custom_filters.maqsad(object()), "")

    def test_scalar_input_returns_empty_string(self):
        for scalar in (0, "", 12345, True, [], {}, "Maqsad: foyda"):
            with self.subTest(scalar=scalar):
                self.assertEqual(custom_filters.maqsad(scalar), "")

    def test_string_desc_gets_prefix_treatment_via_duck_typing(self):
        # a bare string is accepted: getattr(str, 'desc') fails -> ''
        self.assertEqual(custom_filters.maqsad("Maqsad: foyda"), "")


class FilterRegistrationTests(TestCase):
    """All four filters are registered under the exact template names used."""

    def render(self, template_src, value):
        return Template(template_src).render(Context({"x": value}))

    def test_format_currency_registered(self):
        self.assertEqual(
            self.render("{% load custom_filters %}{{ x|format_currency }}", 1000000),
            "1 000 000",
        )

    def test_get_item_registered(self):
        self.assertEqual(
            self.render(
                "{% load custom_filters %}{{ x|get_item:'a' }}",
                {"a": "hit"},
            ),
            "hit",
        )

    def test_get_item_miss_renders_key(self):
        self.assertEqual(
            self.render("{% load custom_filters %}{{ x|get_item:'zz' }}", {}),
            "zz",
        )

    def test_pending_summary_registered(self):
        self.assertEqual(
            self.render(
                "{% load custom_filters %}{{ x|pending_summary }}",
                {"total_uzs": 60000, "total_usd": 0, "total_rub": 0, "total_eur": 5},
            ),
            "60 000 so&#x27;m, 5 €",
        )

    def test_maqsad_registered(self):
        class R:
            desc = "Maqsad: foyda — comment"

        self.assertEqual(
            self.render("{% load custom_filters %}{{ x|maqsad }}", R()),
            "foyda",
        )

    def test_filters_are_plain_python_callables(self):
        for name in ("format_currency", "get_item", "pending_summary", "maqsad"):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(custom_filters, name)))


class FilterFaultToleranceMatrixTests(TestCase):
    """No filter raises on any scalar garbage input (template never 500s)."""

    GARBAGE = (
        None, "", "   ", "abc", "€₽ so'm — 5%", "12345", "12,34.56.7",
        0, 0.0, -1, 1e15, float("nan"), float("inf"), True, False,
        Decimal("NaN"), Decimal("Infinity"), Decimal("9999999999999.99"),
        b"bytes", [], ["x"], {}, {"k": "v"}, object(),
    )

    def assert_no_raise(self, func):
        for value in self.GARBAGE:
            with self.subTest(value=repr(value)):
                try:
                    func(value)
                except Exception as exc:  # pragma: no cover - failure path
                    self.fail(f"raised {type(exc).__name__}: {exc}")

    def test_format_currency_never_raises(self):
        self.assert_no_raise(custom_filters.format_currency)

    def test_get_item_never_raises(self):
        # get_item takes (dictionary, key); exercise scalar garbage as dict
        for value in self.GARBAGE:
            with self.subTest(value=repr(value)):
                try:
                    custom_filters.get_item(value, "k")
                except Exception as exc:  # pragma: no cover - failure path
                    self.fail(f"raised {type(exc).__name__}: {exc}")

    def test_pending_summary_never_raises(self):
        self.assert_no_raise(custom_filters.pending_summary)

    def test_maqsad_never_raises(self):
        self.assert_no_raise(custom_filters.maqsad)

    def test_all_filters_render_garbage_in_template(self):
        # end-to-end: template rendering swallows every garbage value
        src = (
            "{% load custom_filters %}"
            "{{ x|format_currency }}|{{ x|pending_summary }}|{{ x|maqsad }}"
        )
        for value in self.GARBAGE:
            with self.subTest(value=repr(value)):
                try:
                    Template(src).render(Context({"x": value}))
                except Exception as exc:  # pragma: no cover - failure path
                    self.fail(f"template render raised {type(exc).__name__}: {exc}")


class FiltersWithPersistedModelsTests(TestCase):
    """Filters work on real DailyReport values coming out of the database."""

    @classmethod
    def setUpTestData(cls):
        cls.operator = make_operator("tag_report_ops")

    def make_report(self, **kwargs):
        defaults = dict(
            type="income",
            date=timezone.now().date(),
            operator=self.operator,
            category="kassa",
        )
        defaults.update(kwargs)
        return DailyReport.objects.create(**defaults)

    def test_pending_summary_on_persisted_report(self):
        report = self.make_report(
            total_uzs=Decimal("60000.00"),
            total_usd=Decimal("0.00"),
            total_eur=Decimal("5.00"),
        )
        self.assertEqual(custom_filters.pending_summary(report), "60 000 so'm, 5 €")

    def test_format_currency_on_persisted_decimal_field(self):
        report = self.make_report(total_uzs=Decimal("1234.50"))
        self.assertEqual(custom_filters.format_currency(report.total_uzs), "1 234")

    def test_maqsad_on_persisted_report(self):
        report = self.make_report(desc="Maqsad: tushum — keltirilgan")
        self.assertEqual(custom_filters.maqsad(report), "tushum")

    def test_null_total_fields_yield_empty_summary(self):
        report = self.make_report()
        self.assertEqual(custom_filters.pending_summary(report), "")

    def test_null_desc_yields_empty_maqsad(self):
        report = self.make_report()
        self.assertEqual(custom_filters.maqsad(report), "")

    def test_max_digits15_roundtrip(self):
        report = self.make_report(total_uzs=Decimal("9999999999999.99"))
        self.assertEqual(
            custom_filters.format_currency(report.total_uzs),
            "10 000 000 000 000",
        )
