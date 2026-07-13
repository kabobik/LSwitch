"""Focused tests for optional system dictionaries in scripts/install.sh."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


INSTALL_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"


def _run_sourced_script(
    body: str,
    *args: Path | str,
    input_text: str | None = None,
    home: Path,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({"HOME": str(home), "USER": "lswitch-test"})
    return subprocess.run(
        [
            "bash",
            "-c",
            f'source "$1"\nshift\n{body}',
            "bash",
            str(INSTALL_SCRIPT),
            *(str(arg) for arg in args),
        ],
        check=True,
        capture_output=True,
        text=True,
        input=input_text,
        env=env,
    )


@pytest.mark.parametrize(
    ("manager", "dependency", "expected"),
    [
        ("apt", "dictionary_en", "hunspell-en-us"),
        ("apt", "dictionary_ru", "hunspell-ru"),
        ("pacman", "dictionary_en", "hunspell-en_us"),
        ("pacman", "dictionary_ru", "hunspell-ru"),
    ],
)
def test_dictionary_package_mapping(
    manager,
    dependency,
    expected,
    tmp_path,
):
    result = _run_sourced_script(
        'package_for_dependency "$1" "$2"',
        manager,
        dependency,
        home=tmp_path,
    )

    assert result.stdout.strip() == expected


def test_dictionary_discovery_matches_loader_language_priority(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "en_US-large.dic").touch()
    (second / "en_GB.dic").touch()
    (first / "ru_RU_yo.dic").touch()

    result = _run_sourced_script(
        """
SYSTEM_DICTIONARY_DIRS=("$1" "$2")
find_system_dictionary en
find_system_dictionary ru
""",
        first,
        second,
        home=tmp_path,
    )

    assert result.stdout.splitlines() == [
        str(second / "en_GB.dic"),
        str(first / "ru_RU_yo.dic"),
    ]


def test_offer_installs_only_missing_dictionary(tmp_path):
    dictionary_dir = tmp_path / "hunspell"
    dictionary_dir.mkdir()
    (dictionary_dir / "en_US.dic").touch()

    result = _run_sourced_script(
        """
dictionary_dir="$1"
SYSTEM_DICTIONARY_DIRS=("$dictionary_dir")
detect_pkg_manager() { echo "apt"; }
install_system_packages() {
    printf 'PACKAGES:%s\\n' "$*"
    touch "$dictionary_dir/ru_RU.dic"
}
offer_system_dictionaries
""",
        dictionary_dir,
        input_text="\n",
        home=tmp_path,
    )

    assert "PACKAGES:apt hunspell-ru" in result.stdout
    assert "hunspell-en-us" not in result.stdout
    assert "Системные словари установлены" in result.stdout


def test_declining_dictionary_offer_keeps_install_optional(tmp_path):
    dictionary_dir = tmp_path / "hunspell"
    dictionary_dir.mkdir()

    result = _run_sourced_script(
        """
SYSTEM_DICTIONARY_DIRS=("$1")
detect_pkg_manager() { echo "apt"; }
install_system_packages() { echo "UNEXPECTED INSTALL"; return 99; }
offer_system_dictionaries
""",
        dictionary_dir,
        input_text="n\n",
        home=tmp_path,
    )

    assert "UNEXPECTED INSTALL" not in result.stdout
    assert "Установка словарей пропущена" in result.stdout
    assert "префиксная конвертация будет недоступна" in result.stdout


def test_dictionary_package_failure_does_not_abort_install(tmp_path):
    dictionary_dir = tmp_path / "hunspell"
    dictionary_dir.mkdir()

    result = _run_sourced_script(
        """
SYSTEM_DICTIONARY_DIRS=("$1")
detect_pkg_manager() { echo "apt"; }
install_system_packages() { return 42; }
offer_system_dictionaries
echo "INSTALL CONTINUES"
""",
        dictionary_dir,
        input_text="y\n",
        home=tmp_path,
    )

    assert "Не удалось установить системные словари" in result.stdout
    assert "INSTALL CONTINUES" in result.stdout
