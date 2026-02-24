"""Tests for lswitch.i18n — translation and language detection."""

from __future__ import annotations

import os
from unittest import mock

import pytest


class TestI18nClass:
    """Tests for the I18n class."""

    def _make_i18n(self, lang_env: str | None = None):
        """Create a fresh I18n instance with optional LANG override."""
        env = os.environ.copy()
        if lang_env is not None:
            env['LANG'] = lang_env
        else:
            env.pop('LANG', None)
        with mock.patch.dict(os.environ, env, clear=True):
            from lswitch.i18n import I18n
            return I18n()

    def test_t_returns_string_not_key(self):
        """t('lswitch_control') should return a human-readable string, not the key itself."""
        i18n = self._make_i18n('en_US.UTF-8')
        result = i18n.t('lswitch_control')
        assert isinstance(result, str)
        assert result != 'lswitch_control'
        assert len(result) > 0

    def test_t_with_kwargs_substitution(self):
        """t('about_title', version='2.0') should substitute the parameter."""
        i18n = self._make_i18n('en_US.UTF-8')
        result = i18n.t('about_title', version='2.0')
        assert '2.0' in result

    def test_t_fallback_for_nonexistent_key(self):
        """t('nonexistent_key') should return the key itself as fallback."""
        i18n = self._make_i18n('en_US.UTF-8')
        result = i18n.t('nonexistent_key')
        assert result == 'nonexistent_key'

    def test_t_template_without_kwargs_no_crash(self):
        """t('about_title') without kwargs should not crash even if template expects params."""
        i18n = self._make_i18n('en_US.UTF-8')
        result = i18n.t('about_title')
        # Should return the template string as-is (with {version} placeholder)
        assert isinstance(result, str)
        assert '{version}' in result

    def test_get_lang_returns_ru_or_en(self):
        """get_lang() should return 'ru' or 'en'."""
        i18n = self._make_i18n('en_US.UTF-8')
        assert i18n.get_lang() in ('ru', 'en')

    def test_lang_detection_ru(self):
        """LANG=ru_RU.UTF-8 should detect language as 'ru'."""
        i18n = self._make_i18n('ru_RU.UTF-8')
        assert i18n.get_lang() == 'ru'

    def test_lang_detection_en(self):
        """LANG=en_US.UTF-8 should detect language as 'en'."""
        i18n = self._make_i18n('en_US.UTF-8')
        assert i18n.get_lang() == 'en'

    def test_fallback_to_en_without_env(self):
        """Without LANG env var, fallback to 'en'."""
        env = os.environ.copy()
        env.pop('LANG', None)
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch('locale.getlocale', return_value=(None, None)):
            from lswitch.i18n import I18n
            i18n = I18n()
        assert i18n.get_lang() == 'en'

    def test_ru_translations_exist(self):
        """Russian translations should have the same keys as English."""
        i18n = self._make_i18n('ru_RU.UTF-8')
        result = i18n.t('lswitch_control')
        assert result != 'lswitch_control'
        assert isinstance(result, str)

    def test_multiple_kwargs(self):
        """t() with multiple kwargs should substitute all of them."""
        i18n = self._make_i18n('en_US.UTF-8')
        result = i18n.t('about_de_info', de='GNOME', display='X11')
        assert 'GNOME' in result
        assert 'X11' in result

    def test_t_wrong_kwargs(self):
        """t() with wrong format kwargs returns template string."""
        i18n = self._make_i18n('en_US.UTF-8')
        result = i18n.t('about_title', wrong_key='x')
        assert '{version}' in result  # template not substituted but no crash

    def test_en_ru_key_parity(self):
        """All EN keys must exist in RU and vice versa."""
        i18n = self._make_i18n('en_US.UTF-8')
        en_keys = set(i18n._translations['en'].keys())
        ru_keys = set(i18n._translations['ru'].keys())
        assert en_keys == ru_keys


class TestGlobalFunctions:
    """Tests for module-level t() and get_lang() functions."""

    def test_global_t_works(self):
        """Module-level t() should work and return a string."""
        from lswitch.i18n import t
        result = t('lswitch_control')
        assert isinstance(result, str)
        assert result != 'lswitch_control'

    def test_global_get_lang_works(self):
        """Module-level get_lang() should return 'ru' or 'en'."""
        from lswitch.i18n import get_lang
        result = get_lang()
        assert result in ('ru', 'en')
