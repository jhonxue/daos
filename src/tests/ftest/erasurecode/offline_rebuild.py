'''
  (C) Copyright 2020-2023 Intel Corporation.
  (C) Copyright 2025 Hewlett Packard Enterprise Development LP

  SPDX-License-Identifier: BSD-2-Clause-Patent
'''
from ec_utils import ErasureCodeIor


class EcodOfflineRebuild(ErasureCodeIor):
    # pylint: disable=too-many-ancestors
    """
    Test Class Description: To validate Erasure code object data after killing
                            single server (offline rebuild).
    :avocado: recursive
    """

    def test_ec_offline_rebuild(self):
        """Jira ID: DAOS-5894.

        Test Description: Test Erasure code object with IOR.
        Use Case: Create the pool, run IOR with supported
                  EC object type class for small and large transfer sizes.
                  kill single server, Wait to finish rebuild,
                  verify all IOR read data and verified.

        :avocado: tags=all,full_regression
        :avocado: tags=hw,large
        :avocado: tags=ec,ec_array,ec_offline_rebuild,rebuild
        :avocado: tags=EcodOfflineRebuild,test_ec_offline_rebuild
        """
        # Write IOR data set with different EC object and different sizes
        self.ior_write_dataset()

        # Kill the last server rank
        self.server_managers[0].stop_ranks([self.server_count - 1], force=True)

        # Wait for rebuild to complete
        self.pool.wait_for_rebuild_to_start()
        self.pool.wait_for_rebuild_to_end()

        # Read IOR data and verify for different EC object and different sizes
        # written before killing the single server
        self.ior_read_dataset()

        # Kill the another server rank
        self.server_managers[0].stop_ranks([self.server_count - 2], force=True)

        # Wait for rebuild to complete
        self.pool.wait_for_rebuild_to_start()
        self.pool.wait_for_rebuild_to_end()

        # Read IOR data and verify for different EC object and different sizes
        # written before killing the second server.
        # Only +2 (Parity) data will be intact so read and verify only +2 IOR
        # data set
        self.ior_read_dataset(parity=2)
