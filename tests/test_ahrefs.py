"""Tests for tools/ahrefs.py — pure helpers (no network)."""

from __future__ import annotations

import os

import pytest

from tools.ahrefs import _get_token


def test_get_token_uses_argument_when_provided():
    assert _get_token("explicit-token") == "explicit-token"


def test_get_token_reads_env_var(monkeypatch):
    monkeypatch.setenv("AHREFS_API_TOKEN", "env-token")
    assert _get_token() == "env-token"


def test_get_token_argument_wins_over_env(monkeypatch):
    monkeypatch.setenv("AHREFS_API_TOKEN", "env-token")
    assert _get_token("override") == "override"


def test_get_token_raises_when_missing(monkeypatch):
    monkeypatch.delenv("AHREFS_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="AHREFS_API_TOKEN"):
        _get_token()
