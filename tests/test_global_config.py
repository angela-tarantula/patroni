
import unittest

from patroni import global_config
from patroni.dcs import Cluster, ClusterConfig, ClusterMaintenance, Status, SyncState


def get_cluster(config, maintenance):
    return Cluster(None, config, None, Status.empty(), [], None, SyncState.empty(), None, None,
                   maintenance=maintenance)


CONFIGS = {'valid, paused': ClusterConfig(1, {'pause': True, 'ttl': 30}, 1),
           'valid, resumed': ClusterConfig(1, {'ttl': 30}, 1),
           'unparsable': ClusterConfig(1, {}, 0),
           'missing': None}
MIRRORS = {'paused': ClusterMaintenance(2, {'pause': True}),
           'resumed': ClusterMaintenance(2, {'pause': False}),
           'no decision': ClusterMaintenance(2, {}),
           'absent': None}


class TestGlobalConfig(unittest.TestCase):

    @staticmethod
    def new(cached):
        # a fresh object, because the module-level one is shared with other tests
        config = type(global_config)()
        config.update(None, {'pause': True, 'ttl': 25} if cached else {'ttl': 25})
        return config

    def test_mirror_decides_while_config_is_missing(self):
        config = self.new(cached=True)
        config.update(get_cluster(None, ClusterMaintenance(1, {'pause': False})))
        self.assertFalse(config.is_paused)

    def test_pause_resolution(self):
        # /config while it is valid, otherwise the mirror if it holds a decision, otherwise the cached value
        for cached in (True, False):
            for config_name, config in CONFIGS.items():
                for mirror_name, mirror in MIRRORS.items():
                    with self.subTest(cached=cached, config=config_name, mirror=mirror_name):
                        if config and config.modify_version:
                            expected = config.data.get('pause', False)
                        elif mirror and mirror.pause is not None:
                            expected = mirror.pause
                        else:
                            expected = cached
                        cluster = get_cluster(config, mirror)

                        updated = self.new(cached)
                        updated.update(cluster)
                        self.assertEqual(updated.is_paused, expected)

                        base = self.new(cached)
                        self.assertEqual(base.from_cluster(cluster).is_paused, expected)
                        self.assertEqual(base.is_paused, cached)  # from_cluster() leaves its caller alone

    def test_other_settings_keep_their_cached_values(self):
        default = {'pause': True, 'ttl': 25}
        config = type(global_config)()
        config.update(None, default)
        config.update(get_cluster(None, ClusterMaintenance(1, {'pause': False})))
        self.assertEqual(config.get('ttl'), 25)
        self.assertEqual(default, {'pause': True, 'ttl': 25})  # the cached configuration is not rewritten

    def test_mirror_lost_after_it_decided(self):
        # the node keeps the last decision it acted on, as it keeps the last /config it saw
        config = self.new(cached=True)
        config.update(get_cluster(None, ClusterMaintenance(1, {'pause': False})))
        config.update(get_cluster(None, None))
        self.assertFalse(config.is_paused)
