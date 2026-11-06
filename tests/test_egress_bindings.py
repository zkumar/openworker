"""F-010 t02 — a receipt goes to its binding, and a failing sink backs off then dead-letters."""

import pathlib

from coworker.channels.bindings import MAX_ATTEMPTS, BindingStore, DeliveryLedger


def _bindings(tmp_path):
    return BindingStore(str(pathlib.Path(tmp_path) / "b.sqlite"))


def test_a_receipt_goes_to_its_binding_not_to_everyone(tmp_path):
    b = _bindings(tmp_path)
    b.set("webhook", "acme", "slack:C0123")
    b.set("webhook", "beta", "slack:C9999")
    assert b.resolve("webhook", "acme") == "slack:C0123"
    assert b.resolve("webhook", "beta") == "slack:C9999"


def test_an_unbound_channel_has_no_target(tmp_path):
    assert _bindings(tmp_path).resolve("webhook", "nobody") is None


def test_a_binding_can_be_withdrawn(tmp_path):
    b = _bindings(tmp_path)
    b.set("webhook", "acme", "slack:C0123")
    assert b.unset("webhook", "acme") is True
    assert b.resolve("webhook", "acme") is None


def test_delivery_backs_off_then_dead_letters(tmp_path):
    led = DeliveryLedger(str(pathlib.Path(tmp_path) / "d.sqlite"))
    for _ in range(MAX_ATTEMPTS - 1):
        assert led.failed("PA-1", "slack", "timeout") == "pending"
    assert led.failed("PA-1", "slack", "timeout") == "dead"
    dead = led.dead_letters()
    assert len(dead) == 1 and dead[0]["attempts"] == MAX_ATTEMPTS


def test_a_delivered_receipt_leaves_no_dead_letter(tmp_path):
    led = DeliveryLedger(str(pathlib.Path(tmp_path) / "d.sqlite"))
    led.delivered("PA-2", "file")
    assert led.dead_letters() == []
