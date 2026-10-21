# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Test the telemetry initialization."""

import os
import pathlib
import sys
import unittest
from unittest import mock

# Add depot_tools to sys.path to allow importing infra_lib
current_path = pathlib.Path(__file__).resolve()
depot_tools_path = current_path.parent.parent.parent
if str(depot_tools_path) not in sys.path:
    sys.path.insert(0, str(depot_tools_path))

import infra_lib.telemetry as telemetry
from infra_lib.telemetry import config


class InitializeTest(unittest.TestCase):
    """Test telemetry initialization."""

    @mock.patch.dict(os.environ, {'SWARMING_BOT_ID': 'bot-123'})
    @mock.patch('infra_lib.telemetry.config.Config')
    def test_initialize_skips_on_swarming(self, mock_config) -> None:
        """Test initialize skips when SWARMING_BOT_ID is set."""
        telemetry.initialize('test-service')
        # If it returned early, config should not have been instantiated
        mock_config.assert_not_called()

    @mock.patch.dict(os.environ, {}, clear=True)
    @mock.patch('infra_lib.telemetry.config.Config')
    @mock.patch('infra_lib.telemetry.is_google_host')
    def test_initialize_runs_when_not_swarming(self, mock_is_google_host,
                                               mock_config) -> None:
        """Test initialize proceeds when SWARMING_BOT_ID is not set."""
        mock_is_google_host.return_value = True
        mock_cfg = mock.Mock()
        mock_config.return_value = mock_cfg
        # Make it return a mock config that is disabled to avoid full init side effects
        mock_cfg.trace_config.disabled.return_value = True

        telemetry.initialize('test-service')

        mock_config.assert_called_once()


if __name__ == '__main__':
    unittest.main()
