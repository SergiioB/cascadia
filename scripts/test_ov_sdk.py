"""Offline tests for scripts/ov_sdk.py (the URL layout rules, no network).

    python3 -m unittest scripts/test_ov_sdk.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ov_sdk  # noqa: E402

P = ov_sdk.BASE


class Channel(unittest.TestCase):
    def test_stable_beta_nightly(self):
        self.assertEqual(ov_sdk.channel("2026.4.1.0"), "stable")
        self.assertEqual(ov_sdk.channel("2026.5.0.0beta1"), "beta")
        self.assertEqual(ov_sdk.channel("2026.5.0.0rc1"), "beta")
        self.assertEqual(ov_sdk.channel("2026.5.0.0.dev20260925"), "nightly")


class StableDirs(unittest.TestCase):
    def test_trims_trailing_zero_components_but_keeps_major_minor(self):
        self.assertEqual(ov_sdk.stable_dir_names("2026.4.1.0"), ["2026.4.1", "2026.4.1.0"])
        self.assertEqual(ov_sdk.stable_dir_names("2026.4.0.0"), ["2026.4", "2026.4.0.0"])
        self.assertEqual(ov_sdk.stable_dir_names("2026.2.0.0"), ["2026.2", "2026.2.0.0"])
        # Intel kept the full name for this one; it must be a candidate too.
        self.assertEqual(ov_sdk.stable_dir_names("2026.1.2.0"), ["2026.1.2", "2026.1.2.0"])
        self.assertEqual(ov_sdk.stable_dir_names("2026.0.0.0"), ["2026.0", "2026.0.0.0"])


class Candidates(unittest.TestCase):
    def test_stable_linux(self):
        self.assertEqual(
            ov_sdk.candidate_urls("2026.4.1.0", "linux", "ubuntu22"),
            [
                f"{P}/2026.4.1/linux/openvino_genai_ubuntu22_2026.4.1.0_x86_64.tar.gz",
                f"{P}/2026.4.1.0/linux/openvino_genai_ubuntu22_2026.4.1.0_x86_64.tar.gz",
            ],
        )

    def test_current_release_pin_matches_the_old_hand_written_url(self):
        # The URL release.yml carried before the version became a single string.
        self.assertEqual(
            ov_sdk.candidate_urls("2026.2.0.0", "windows", None)[0],
            f"{P}/2026.2/windows/openvino_genai_windows_2026.2.0.0_x86_64.zip",
        )
        self.assertEqual(
            ov_sdk.candidate_urls("2026.2.0.0", "linux", "ubuntu22")[0],
            f"{P}/2026.2/linux/openvino_genai_ubuntu22_2026.2.0.0_x86_64.tar.gz",
        )

    def test_beta_lives_under_beta_with_the_full_version(self):
        self.assertEqual(
            ov_sdk.candidate_urls("2026.5.0.0beta1", "windows", None),
            [f"{P}/beta/2026.5.0.0beta1/windows/openvino_genai_windows_2026.5.0.0beta1_x86_64.zip"],
        )
        self.assertEqual(
            ov_sdk.candidate_urls("2026.5.0.0beta1", "linux", "ubuntu22"),
            [f"{P}/beta/2026.5.0.0beta1/linux/openvino_genai_ubuntu22_2026.5.0.0beta1_x86_64.tar.gz"],
        )

    def test_nightly_lives_under_nightly(self):
        self.assertEqual(
            ov_sdk.candidate_urls("2026.5.0.0.dev20260925", "linux", "ubuntu24"),
            [f"{P}/nightly/2026.5.0.0.dev20260925/linux/openvino_genai_ubuntu24_2026.5.0.0.dev20260925_x86_64.tar.gz"],
        )

    def test_macos(self):
        self.assertEqual(
            ov_sdk.candidate_urls("2026.4.1.0", "macos", None)[0],
            f"{P}/2026.4.1/macos/openvino_genai_macos_12_6_2026.4.1.0_arm64.tar.gz",
        )

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            ov_sdk.candidate_urls("latest", "linux", "ubuntu22")
        with self.assertRaises(ValueError):
            ov_sdk.candidate_urls("2026.4.1.0/../x", "linux", "ubuntu22")
        with self.assertRaises(ValueError):
            ov_sdk.candidate_urls("2026.4.1.0", "linux", None)  # linux needs a dist
        with self.assertRaises(ValueError):
            ov_sdk.candidate_urls("2026.4.1.0", "plan9", None)


if __name__ == "__main__":
    unittest.main()
