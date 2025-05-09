"""
  (C) Copyright 2020-2023 Intel Corporation.
  (C) Copyright 2025 Hewlett Packard Enterprise Development LP

  SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from nvme_utils import ServerFillUp
from osa_utils import OSAUtils
from test_utils_pool import add_pool
from write_host_file import write_host_file


class OSAOfflineDrain(OSAUtils, ServerFillUp):
    # pylint: disable=too-many-ancestors
    """
    Test Class Description: This test runs
    daos_server offline drain test cases.

    :avocado: recursive
    """

    def setUp(self):
        """Set up for test case."""
        super().setUp()
        self.dmg_command = self.get_dmg_command()
        self.ranks = self.params.get("rank_list", '/run/test_ranks/*')
        self.test_oclass = self.params.get("oclass", '/run/test_obj_class/*')
        self.ior_test_sequence = self.params.get(
            "ior_test_sequence", '/run/ior/iorflags/*')
        # Recreate the client hostfile without slots defined
        self.hostfile_clients = write_host_file(self.hostlist_clients, self.workdir)

    def run_offline_drain_test(self, num_pool, data=False, oclass=None, pool_fillup=0):
        """Run the offline drain without data.

        Args:
            num_pool (int) : total pools to create for testing purposes.
            data (bool) : whether pool has no data or to create some data in pool.
                Defaults to False.
            oclass (str): DAOS object class (eg: RP_2G1,etc)
        """
        # Create a pool
        pool = {}
        target_list = []

        if oclass is None:
            oclass = self.ior_cmd.dfs_oclass.value

        # Exclude target : random two targets  (target idx : 0-7)
        exc = self.random.randint(0, 6)
        target_list.append(exc)
        target_list.append(exc + 1)
        t_string = "{},{}".format(target_list[0], target_list[1])

        for val in range(0, num_pool):
            pool[val] = add_pool(self, connect=False)
            self.pool = pool[val]
            self.pool.set_property("reclaim", "disabled")
            test_seq = self.ior_test_sequence[0]

            if data:
                # if pool_fillup is greater than 0, then
                # use start_ior_load method from nvme_utils.py.
                # Otherwise, use the osa_utils.py run_ior_thread
                # method.
                if pool_fillup > 0:
                    self.ior_cmd.dfs_oclass.update(oclass)
                    self.ior_cmd.dfs_dir_oclass.update(oclass)
                    self.ior_default_flags = self.ior_w_flags
                    self.log.info(self.pool.pool_percentage_used())
                    self.start_ior_load(storage='NVMe', operation="Auto_Write", percent=pool_fillup)
                    self.log.info(self.pool.pool_percentage_used())
                else:
                    self.run_ior_thread("Write", oclass, test_seq)
                    self.run_mdtest_thread(oclass)
                if self.test_with_snapshot is True:
                    # Create a snapshot of the container
                    # after IOR job completes.
                    self.container.create_snap()
                    self.log.info("Created container snapshot: %s", self.container.epoch)
                if self.test_during_aggregation is True:
                    self.run_ior_thread("Write", oclass, test_seq)

        # Drain ranks and targets
        for val in range(0, num_pool):
            # Drain ranks provided in YAML file
            for index, rank in enumerate(self.ranks):
                self.pool = pool[val]
                # If we are testing using multiple pools, reintegrate
                # the rank back and then drain.
                self.pool.display_pool_daos_space("Pool space: Beginning")
                # Get initial total free space (scm+nvme)
                initial_total_space = self.pool.get_total_space(refresh=True)
                pver_begin = self.pool.get_version(True)
                self.log.info("Pool Version at the beginning %s", pver_begin)
                if self.test_during_aggregation is True and index == 0:
                    self.pool.set_property("reclaim", "time")
                    self.delete_extra_container(self.pool)
                    self.simple_osa_reintegrate_loop(rank=rank, action="drain")
                if (self.test_during_rebuild is True and val == 0):
                    # Exclude rank 3
                    self.pool.exclude([3])
                    self.pool.wait_for_rebuild_to_start()
                # If the pool is filled up just drain only a single rank.
                if pool_fillup > 0 and index > 0:
                    continue
                output = self.pool.drain(rank, t_string)
                self.print_and_assert_on_rebuild_failure(output)
                total_space_after_drain = self.pool.get_total_space(refresh=True)

                pver_drain = self.pool.get_version(True)
                self.log.info("Pool Version after drain %d", pver_drain)
                # Check pool version incremented after pool drain
                self.assertGreater(pver_drain, (pver_begin + 1),
                                   "Pool Version Error:  After drain")
                if self.test_during_aggregation is False:
                    self.assertGreater(initial_total_space, total_space_after_drain,
                                       "Expected total space after drain is more than initial")
                if num_pool > 1:
                    output = self.pool.reintegrate(rank, t_string)
                    self.print_and_assert_on_rebuild_failure(output)
                    total_space_after_reintegration = self.pool.get_total_space(refresh=True)
                    self.assertGreater(
                        total_space_after_reintegration, total_space_after_drain,
                        "Expected total space after reintegration is less than drain")
                if (self.test_during_rebuild is True and val == 0):
                    # Reintegrate rank 3
                    output = self.pool.reintegrate("3")
                    self.print_and_assert_on_rebuild_failure(output)
                    total_space_after_reintegration = self.pool.get_total_space(refresh=True)
                    self.assertGreater(
                        total_space_after_reintegration, total_space_after_drain,
                        "Expected total space after reintegration is less than drain")

        for val in range(0, num_pool):
            display_string = "Pool{} space at the End".format(val)
            pool[val].display_pool_daos_space(display_string)
            if data:
                if pool_fillup > 0:
                    self.start_ior_load(storage='NVMe', operation='Auto_Read', percent=pool_fillup)
                else:
                    self.run_ior_thread("Read", oclass, test_seq)
                    self.run_mdtest_thread(oclass)
                    self.container = self.pool_cont_dict[self.pool][0]
                    self.container.daos.env['UCX_LOG_LEVEL'] = 'error'
                    self.container.check()

    def test_osa_offline_drain(self):
        """JIRA ID: DAOS-4750.

        Test Description: Validate Offline Drain

        :avocado: tags=all,pr,daily_regression
        :avocado: tags=hw,medium
        :avocado: tags=osa,osa_drain,offline_drain,checksum,ior
        :avocado: tags=OSAOfflineDrain,test_osa_offline_drain
        """
        self.log.info("Offline Drain : Basic Drain")
        self.run_offline_drain_test(1, True)

    def test_osa_offline_drain_without_checksum(self):
        """Test ID: DAOS-7159.

        Test Description: Validate Offline Drain without enabling checksum in container properties.

        :avocado: tags=all,full_regression
        :avocado: tags=hw,medium
        :avocado: tags=osa,osa_drain,offline_drain
        :avocado: tags=OSAOfflineDrain,test_osa_offline_drain_without_checksum
        """
        self.test_with_checksum = self.params.get("test_with_checksum", "/run/checksum/*")
        self.log.info("Offline Drain : Without Checksum")
        self.run_offline_drain_test(1, data=True)

    def test_osa_offline_drain_during_aggregation(self):
        """Test ID: DAOS-7159.

        Test Description: Validate Offline Drain during aggregation

        :avocado: tags=all,daily_regression
        :avocado: tags=hw,medium
        :avocado: tags=osa,osa_drain,offline_drain,checksum
        :avocado: tags=OSAOfflineDrain,test_osa_offline_drain_during_aggregation
        """
        self.test_during_aggregation = self.params.get(
            "test_with_aggregation", "/run/aggregation/*")
        self.log.info("Offline Drain : During Aggregation")
        self.run_offline_drain_test(1, data=True)

    def test_osa_offline_drain_oclass(self):
        """Test ID: DAOS-7159.

        Test Description: Validate Offline Drain with different object class

        :avocado: tags=all,full_regression
        :avocado: tags=hw,medium
        :avocado: tags=osa,osa_drain,offline_drain
        :avocado: tags=OSAOfflineDrain,test_osa_offline_drain_oclass
        """
        self.test_with_checksum = self.params.get("test_with_checksum", "/run/checksum/*")
        self.log.info("Offline Drain : Oclass")
        for oclass in self.test_oclass:
            self.run_offline_drain_test(1, data=True, oclass=oclass)

    def test_osa_offline_drain_multiple_pools(self):
        """Test ID: DAOS-7159.

        Test Description: Validate Offline Drain with multiple pools

        :avocado: tags=all,full_regression
        :avocado: tags=hw,medium
        :avocado: tags=osa,osa_drain,offline_drain
        :avocado: tags=OSAOfflineDrain,test_osa_offline_drain_multiple_pools
        """
        self.log.info("Offline Drain : Multiple Pools")
        self.run_offline_drain_test(2, data=True)

    def test_osa_offline_drain_during_rebuild(self):
        """Test ID: DAOS-7159.

        Test Description: Validate Offline Drain during rebuild

        :avocado: tags=all,full_regression
        :avocado: tags=hw,medium
        :avocado: tags=osa,osa_drain,offline_drain,rebuild
        :avocado: tags=OSAOfflineDrain,test_osa_offline_drain_during_rebuild
        """
        self.test_during_rebuild = self.params.get("test_with_rebuild", "/run/rebuild/*")
        self.log.info("Offline Drain : During Rebuild")
        self.run_offline_drain_test(1, data=True)

    def test_osa_offline_drain_after_snapshot(self):
        """Test ID: DAOS-8057.

        Test Description: Validate Offline Drain after taking snapshot.

        :avocado: tags=all,daily_regression
        :avocado: tags=hw,medium
        :avocado: tags=osa,osa_drain,offline_drain,checksum
        :avocado: tags=OSAOfflineDrain,test_osa_offline_drain_after_snapshot
        """
        self.test_with_snapshot = self.params.get("test_with_snapshot", "/run/snapshot/*")
        self.log.info("Offline Drain : After taking snapshot")
        self.run_offline_drain_test(1, data=True)

    def test_osa_offline_drain_with_less_pool_space(self):
        """Test ID: DAOS-7160.

        Test Description: Drain rank after with less pool space.

        :avocado: tags=all,full_regression
        :avocado: tags=hw,medium
        :avocado: tags=osa,osa_drain,offline_drain,offline_drain_full
        :avocado: tags=OSAOfflineDrain,test_osa_offline_drain_with_less_pool_space
        """
        self.log.info("Offline Drain : Test with less pool space")
        oclass = self.params.get("pool_test_oclass", '/run/pool_capacity/*')
        pool_fillup = self.params.get("pool_fillup", '/run/pool_capacity/*')
        self.run_offline_drain_test(1, data=True, oclass=oclass, pool_fillup=pool_fillup)
